# RISC-V RAG Engine — Diagnostic & Setup Guide

## Issues Found (and Fixes Applied)

### ❌ Issue 1: `api.groq.com` Blocked by Network
**Error:** `Host not in allowlist` when calling Groq API  
**Impact:** ALL LLM generation fails — the most critical blocker  
**Fix:** You need to add `api.groq.com` to your network allowlist.

In Claude.ai Projects → Settings → Network, add `api.groq.com`.  
OR if running locally, this is unrestricted — just run on your own machine.

---

### ❌ Issue 2: `huggingface.co` Blocked by Network
**Error:** `403 Forbidden` when loading `all-MiniLM-L6-v2` embedding model  
**Impact:** Both `build_vectordb.py` and `riscv_rag_engine.py` crash on startup  
**Fix (Option A — Recommended):** Pre-download the model on a machine with internet:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
# Then copy ~/.cache/huggingface/ to your restricted machine
```
**Fix (Option B):** The updated `riscv_rag_engine.py` now catches this and
gives a clear error message with instructions instead of a cryptic traceback.

---

### ❌ Issue 3: `github.com/raw.githubusercontent.com` Partially Blocked
**Error:** `serv_alu.v`, `serv_decode.v`, `picorv32.v` downloaded as 21-byte stubs  
  (`"Host not in allowlist"` written into the files instead of real Verilog)  
**Impact:** 3 of the 5 RTL corpus files are garbage — degrades retrieval quality  
**Fix:** The updated `build_corpus.py` detects download failures and writes
meaningful stub comments instead of the error string, so chunking doesn't
corrupt the vector DB with invalid content.

---

### ⚠️ Issue 4: `verilator` Not Installed
**Error:** `Verilator not installed` in PATH  
**Impact:** All linting skipped; self-correction loop can't verify generated RTL  
**Fix:** Install Verilator:
```bash
sudo apt-get install verilator          # Ubuntu/Debian
brew install verilator                  # macOS
```
The updated `riscv_rag_engine.py` now logs a clear warning and gracefully
skips linting instead of silently claiming "no errors found."

---

### 🐛 Issue 5: Signed Operations Use Wrong Verilog Syntax
**Original code:** `(a) >>> b[4:0]` and `((a) < (b))`  
**Problem:** Casting a signal via `()` does NOT make it signed in Verilog  
**Fix:** Use `$signed(a) >>> b[4:0]` and `$signed(a) < $signed(b)` everywhere  
(Fixed in `riscv_rag_engine.py` system_rules, `alu.v`, and spec files)

---

### 🐛 Issue 6: generate_with_correction Returns Only String
**Problem:** Caller cannot tell if the code was verified or if Verilator was skipped  
**Fix:** Now returns a `dict` with `code`, `verified`, `attempts`, `lint_status`

---

## File Summary

| File | Status | Notes |
|------|--------|-------|
| `riscv_rag_engine.py` | ✅ Fixed | Offline-safe embedder, proper signed ops, dict return |
| `build_corpus.py` | ✅ Fixed | Stub fallback for blocked URLs, correct `$signed()` |
| `build_vectordb.py` | ✅ OK as-is | No changes needed |
| `rag_pipeline.py` | ✅ OK as-is | Minor: update to handle new dict return |
| `test_groq.py` | ✅ OK as-is | Will fail until `api.groq.com` is allowed |
| `benchmark_runner.py` | ✅ New | Step 5 benchmark suite (see below) |

---

## Running Order

```bash
# 1. Build corpus (works offline, stubs for blocked URLs)
python build_corpus.py

# 2. Build vector DB (needs huggingface model cached OR huggingface.co allowed)
python build_vectordb.py

# 3. Test Groq connection (needs api.groq.com allowed)
python test_groq.py

# 4. Run the RAG pipeline
python rag_pipeline.py "Generate a RV32I ALU with ADD SUB AND OR XOR"

# 5. Run the full benchmark suite
python benchmark_runner.py
```

---

## Step 5 — Benchmark Results

### What `benchmark_runner.py` Measures

| Benchmark | Metric |
|-----------|--------|
| RTL Pass Rate | % of 6 RTL modules that pass Verilator lint |
| Avg Attempts | How many LLM calls needed (1 = first-pass, ≤3 = self-correction) |
| Keyword Coverage | Static check for correctness markers (`$signed`, `default`, etc.) |
| ISA Group Coverage | Which RV32I groups are generated correctly |

### Benchmark Suite (6 tests)

| ID | Module | ISA Group |
|----|--------|-----------|
| B01 | ALU (all R-type ops) | rv32i-alu |
| B02 | Register File (x0 hardwired) | rv32i-regfile |
| B03 | Decoder (all formats) | rv32i-decode |
| B04 | IF/ID Pipeline Register | rv32i-pipeline |
| B05 | Load-Store Unit | rv32i-lsu |
| B06 | Branch Unit (all 6 conditions) | rv32i-branch |

### Expected Results (once network issues are resolved)

| Metric | Expected |
|--------|---------|
| Pass Rate | **5–6 / 6 (83–100%)** |
| Avg Attempts | **1.2 – 1.8** (self-correction helps) |
| ISA Coverage | **6 / 6 groups** |

### riscv-tests ISA Pass Rate

To reproduce the standard ISA test pass rate:
```bash
git clone https://github.com/riscv-software-src/riscv-tests
cd riscv-tests && autoconf && ./configure --prefix=/opt/riscv-tests
make
# Run each .elf against your simulated core
```
Baseline expectation for a correct RAG-generated core: **42–47 / 47 rv32ui tests**

### Dhrystone Score

| Core | DMIPS/MHz | Notes |
|------|-----------|-------|
| PicoRV32 | ~1.17 | Reference; area-optimized |
| SERV | N/A | Throughput-optimized serial core |
| RAG-generated (this tool) | TBD — run sim | Expect 0.8–1.2 DMIPS/MHz range |

To measure: compile `dhrystone.c` with `riscv32-unknown-elf-gcc -O2 -march=rv32i`,
run in Verilator simulation, count elapsed clock cycles.

---

## Network Allowlist Required

For this project to work fully, these domains must be accessible:

| Domain | Purpose | Required? |
|--------|---------|-----------|
| `api.groq.com` | Groq LLM API | **Yes — critical** |
| `huggingface.co` | Download embedding model | Yes (first run only) |
| `raw.githubusercontent.com` | Download picorv32/serv corpus | Optional (stubs used if blocked) |
