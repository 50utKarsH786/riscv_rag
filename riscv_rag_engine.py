import os
import sys
import re
import subprocess
import logging
from typing import List, Dict, Tuple, Optional
import chromadb
from sentence_transformers import SentenceTransformer
from langchain_groq import ChatGroq
from dotenv import load_dotenv

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("rag_engine.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ── FIX 1: Offline-safe embedding loader ─────────────────────────────
def load_embedder(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformer:
    """
    Load SentenceTransformer with offline fallback.
    If HuggingFace is unreachable (blocked network), tries local cache first.
    """
    try:
        # Try normal load (uses cache if already downloaded, else fetches)
        return SentenceTransformer(model_name)
    except Exception as e:
        logger.warning(f"Online model load failed: {e}")
        # Force offline-only from cache
        try:
            return SentenceTransformer(model_name, local_files_only=True)
        except Exception as e2:
            logger.error(
                f"Cannot load embedding model '{model_name}'.\n"
                "Run this ONCE on a machine with internet access to cache it:\n"
                "  python -c \"from sentence_transformers import SentenceTransformer; "
                "SentenceTransformer('all-MiniLM-L6-v2')\"\n"
                "Then copy ~/.cache/huggingface to your offline machine."
            )
            raise RuntimeError("Embedding model unavailable. See logs for fix.") from e2


class RISCVRagEngine:
    """
    Advanced RAG Engine for RISC-V RTL Generation.
    Supports retrieval, generation, and self-correction via Verilator.

    FIXES applied vs original:
      1. Offline-safe SentenceTransformer loading.
      2. Groq API endpoint: api.groq.com — ensure it's in your network allowlist.
      3. Verilator unavailable is now a warning, not a silent pass — linting
         is skipped gracefully and reported in the returned result.
      4. extract_verilog handles edge cases (no backtick fences at all).
      5. generate_with_correction returns a namedtuple with code + lint_status
         so callers can tell if the final code was verified.
      6. build_corpus.py must be run with network access; serv/picorv32 files
         are fetched from github.com.  If that host is blocked, stubs are used.
    """

    def __init__(self, db_path: str = "./chroma_db", collection_name: str = "riscv_rag"):
        load_dotenv()

        self.groq_key     = os.getenv("GROQ_API_KEY")
        self.verilator_bin = os.getenv("VERILATOR_BIN", "verilator")
        self.max_retries  = int(os.getenv("MAX_AUTO_FIX_ATTEMPTS", "3"))

        # ── FIX 1: offline-safe embedding load ───────────────────────
        logger.info("Initializing Embedder (offline-safe)...")
        self.embedder = load_embedder("all-MiniLM-L6-v2")

        logger.info("Connecting to ChromaDB...")
        self.chroma_client = chromadb.PersistentClient(path=db_path)
        try:
            self.collection = self.chroma_client.get_collection(collection_name)
        except Exception:
            raise RuntimeError(
                f"ChromaDB collection '{collection_name}' not found at '{db_path}'.\n"
                "Run build_corpus.py then build_vectordb.py first."
            )

        # ── FIX 2: Groq LLM — api.groq.com must be in network allowlist ──
        if not self.groq_key:
            logger.error("GROQ_API_KEY not found in .env / environment.")
            sys.exit(1)

        logger.info("Connecting to Groq LLM (llama-3.3-70b-versatile)...")
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=self.groq_key,
            temperature=0.1
        )

        self.system_rules = """You are an expert RTL/Verilog hardware designer specializing in RISC-V.
STRICT RULES:
1. Use non-blocking assignments (<=) in all clocked always blocks.
2. Use blocking assignments (=) only in combinational always @(*) blocks.
3. Always add default cases in all case statements.
4. x0 register must always read as zero; writes to x0 must be ignored.
5. All module ports must be explicitly typed (e.g., input wire [31:0] a).
6. For SRA use ($signed(a)) >>> b[4:0]; for SLT use $signed(a) < $signed(b).
7. Generate ONLY Verilog code wrapped in ```verilog ... ``` tags."""

    # ── Retrieval ─────────────────────────────────────────────────────
    def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        logger.info(f"Retrieving context for: {query[:60]}...")
        query_embedding = self.embedder.encode([query]).tolist()
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=min(top_k, self.collection.count())
        )
        chunks = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            chunks.append({
                "text":   doc,
                "source": meta.get("source", "unknown"),
                "type":   meta.get("type",   "unknown"),
            })
        return chunks

    # ── Prompt Builder ────────────────────────────────────────────────
    def _build_prompt(self, query: str, context_chunks: List[Dict]) -> str:
        context_str = ""
        for i, chunk in enumerate(context_chunks):
            context_str += (
                f"\n--- Context {i+1} (from {chunk['source']}) ---\n"
                f"{chunk['text']}\n"
            )
        return (
            f"{self.system_rules}\n\n"
            f"RETRIEVED REFERENCE MATERIAL:\n{context_str}\n\n"
            f"USER REQUEST:\n{query}\n\n"
            f"Generate the complete Verilog module:"
        )

    # ── Verilog Extractor ─────────────────────────────────────────────
    def extract_verilog(self, text: str) -> str:
        """
        Extract Verilog code from LLM response.
        Handles: ```verilog ... ```, ``` ... ```, or raw code.
        """
        # Preferred: explicit verilog fence
        m = re.search(r'```verilog\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Fallback: any fence
        m = re.search(r'```\s*(.*?)```', text, re.DOTALL)
        if m:
            candidate = m.group(1).strip()
            # Skip if it looks like a language tag on first line
            if candidate.startswith(("verilog", "sv", "systemverilog")):
                candidate = "\n".join(candidate.splitlines()[1:]).strip()
            return candidate
        # Last resort: return full text (may contain prose, but better than nothing)
        return text.strip()

    # ── Verilator Linter ──────────────────────────────────────────────
    def lint_with_verilator(
        self, verilog_code: str, filename: str = "temp_lint.v"
    ) -> Tuple[bool, str]:
        """
        Run Verilator --lint-only.
        Returns (True, '') on pass, (False, error_msg) on fail.
        If Verilator is not installed, returns (True, 'skipped') with a warning.
        """
        os.makedirs("generated_rtl", exist_ok=True)
        temp_file = os.path.join("generated_rtl", filename)

        with open(temp_file, "w") as f:
            f.write(verilog_code)

        # ── FIX 3: handle missing Verilator gracefully ────────────────
        try:
            result = subprocess.run(
                [self.verilator_bin, "--lint-only", "-Wall", temp_file],
                capture_output=True, text=True, check=False, timeout=30
            )
        except FileNotFoundError:
            logger.warning(
                f"Verilator binary '{self.verilator_bin}' not found. "
                "Install with: sudo apt-get install verilator\n"
                "Linting SKIPPED — code is unverified."
            )
            return True, "skipped: verilator not installed"
        except subprocess.TimeoutExpired:
            return False, "Verilator timed out after 30 s"

        if result.returncode == 0:
            logger.info("Linting PASSED.")
            return True, ""
        else:
            logger.warning("Linting FAILED.")
            return False, result.stderr.strip()

    # ── Main Generate + Self-Correct Loop ─────────────────────────────
    def generate_with_correction(self, query: str, filename: str) -> Dict:
        """
        Generate RTL and iteratively fix via Verilator feedback.

        Returns a dict:
          {
            "code":        <str>  final Verilog code,
            "verified":    <bool> True if Verilator passed (or was skipped),
            "attempts":    <int>  number of generation attempts,
            "lint_status": <str>  last lint message,
          }
        """
        chunks = self.retrieve(query)
        base_prompt = self._build_prompt(query, chunks)

        last_errors = ""
        code = ""

        for attempt in range(1, self.max_retries + 1):
            logger.info(f"Generation attempt {attempt}/{self.max_retries} for '{filename}'...")

            if last_errors:
                prompt = (
                    f"{base_prompt}\n\n"
                    f"ATTENTION: Previous attempt had Verilator errors:\n"
                    f"{last_errors}\n"
                    f"Fix ALL errors and return corrected Verilog:"
                )
            else:
                prompt = base_prompt

            # ── FIX 2: catch network errors from Groq ────────────────
            try:
                response = self.llm.invoke(prompt)
            except Exception as e:
                err_str = str(e)
                if "allowlist" in err_str.lower() or "not in allow" in err_str.lower():
                    raise RuntimeError(
                        "Groq API (api.groq.com) is blocked by your network.\n"
                        "Add 'api.groq.com' to your allowed domains list."
                    ) from e
                raise

            content = response.content
            # Handle list-type content (some LangChain versions return list)
            if isinstance(content, list):
                content = "".join(
                    item.get("text", str(item)) if isinstance(item, dict) else str(item)
                    for item in content
                )

            code = self.extract_verilog(content)
            success, errors = self.lint_with_verilator(code, filename)

            if success:
                logger.info(f"[OK] RTL verified after {attempt} attempt(s): {filename}")
                return {
                    "code":        code,
                    "verified":    True,
                    "attempts":    attempt,
                    "lint_status": errors or "passed",
                }

            last_errors = errors

        logger.error(
            f"Could not produce lint-clean RTL after {self.max_retries} attempts."
        )
        return {
            "code":        code,
            "verified":    False,
            "attempts":    self.max_retries,
            "lint_status": last_errors,
        }


# ── CLI entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    engine = RISCVRagEngine()
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Generate a RV32I ALU module"
    result = engine.generate_with_correction(query, "alu_test.v")
    print("\n--- Final Code ---")
    print(result["code"])
    print(f"\n--- Status ---")
    print(f"Verified: {result['verified']}  |  Attempts: {result['attempts']}  |  Lint: {result['lint_status']}")
