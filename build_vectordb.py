import os
import re
import chromadb
from sentence_transformers import SentenceTransformer

# ── Init ChromaDB ──────────────────────────────────────────────────────
chroma_client = chromadb.PersistentClient(path="./chroma_db")
try:
    chroma_client.delete_collection("riscv_rag")
except:
    pass

collection = chroma_client.create_collection(
    name="riscv_rag",
    metadata={"hnsw:space": "cosine"}
)

# ── Load embedding model ───────────────────────────────────────────────
print("Loading embedding model...")
embedder = SentenceTransformer("all-MiniLM-L6-v2")
print("  Model loaded.")

# ── Chunking functions ─────────────────────────────────────────────────
def chunk_verilog(text, filename):
    chunks = []
    parts = re.split(r'(?=\bmodule\b)', text)
    for part in parts:
        part = part.strip()
        if len(part) < 50:
            continue
        if len(part) > 1500:
            sub_chunks = [part[i:i+1500] for i in range(0, len(part), 1200)]
            for sc in sub_chunks:
                chunks.append({"text": sc, "source": filename, "type": "verilog_module"})
        else:
            chunks.append({"text": part, "source": filename, "type": "verilog_module"})
    return chunks

def chunk_markdown(text, filename):
    chunks = []
    parts = re.split(r'(?=^## )', text, flags=re.MULTILINE)
    for part in parts:
        part = part.strip()
        if len(part) < 30:
            continue
        if len(part) > 1500:
            sub_chunks = [part[i:i+1500] for i in range(0, len(part), 1200)]
            for sc in sub_chunks:
                chunks.append({"text": sc, "source": filename, "type": "markdown_section"})
        else:
            chunks.append({"text": part, "source": filename, "type": "markdown_section"})
    return chunks

# ── Walk corpus and chunk ──────────────────────────────────────────────
all_chunks = []

for root, dirs, files in os.walk("corpus"):
    for fname in files:
        fpath = os.path.join(root, fname)
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        print(f"Chunking {fpath}...")
        if fname.endswith(".v"):
            chunks = chunk_verilog(text, fname)
        elif fname.endswith(".md"):
            chunks = chunk_markdown(text, fname)
        else:
            continue
        print(f"  -> {len(chunks)} chunks")
        all_chunks.extend(chunks)

print(f"\nTotal chunks: {len(all_chunks)}")

# ── Assign globally unique IDs ─────────────────────────────────────────
for i, chunk in enumerate(all_chunks):
    chunk["chunk_id"] = f"chunk_{i:04d}"

# ── Embed and store ────────────────────────────────────────────────────
print("\nEmbedding and storing in ChromaDB...")

BATCH_SIZE = 50
for i in range(0, len(all_chunks), BATCH_SIZE):
    batch = all_chunks[i:i+BATCH_SIZE]
    texts      = [c["text"]     for c in batch]
    ids        = [c["chunk_id"] for c in batch]
    metadatas  = [{"source": c["source"], "type": c["type"]} for c in batch]
    embeddings = embedder.encode(texts).tolist()

    collection.add(
        ids=ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas
    )
    print(f"  Stored batch {i//BATCH_SIZE + 1} ({len(batch)} chunks)")

print(f"\nDone! {collection.count()} chunks stored in ChromaDB.")

# ── Quick retrieval test ───────────────────────────────────────────────
print("\nTesting retrieval...")
test_query = "how to implement ALU for RISC-V with ADD SUB AND OR operations"
query_embedding = embedder.encode([test_query]).tolist()

results = collection.query(
    query_embeddings=query_embedding,
    n_results=3
)

print(f"\nQuery: '{test_query}'")
print("Top 3 retrieved chunks:")
for i, (doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
    print(f"\n  [{i+1}] Source: {meta['source']} | Type: {meta['type']}")
    print(f"       Preview: {doc[:200]}...")
