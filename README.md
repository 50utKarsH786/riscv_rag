# RISC-V RAG Pipeline for RTL Generation

This repository implements a **Retrieval-Augmented Generation (RAG)** pipeline specifically designed to generate correct, synthesizable Verilog RTL for a RISC-V RV32I in-order processor.

Developed for the **Fermions ML Intern Case Study**.

---

## 🚀 Key Features and Pipeline Robustness

1. **Self-Correcting Engine**: Uses **Verilator** to lint generated Verilog modules behind the scenes. If structural errors are found, the engine automatically feeds them back to the LLM (Llama-3.3-70b) to "self-heal" the code before final output.
2. **Network-Resilient Corpus**: The `build_corpus.py` script gracefully handles network blocks (e.g., blocked GitHub access) by generating minimal stubs, preventing Vector Database corruption.
3. **Offline Embedding**: Uses an embedding pipeline (`all-MiniLM-L6-v2`) caching fallback that works even if upstream HuggingFace API access is heavily restricted.
4. **Hardware Rule Enforcement**: Forces hard RTL rules through the core system prompt, ensuring the LLM uses correct syntax like `$signed()` casting for arithmetic operations.

## 🛠️ Project Structure

- `riscv_rag_engine.py`: The core RAG engine with the self-correction loop.
- `build_corpus.py`: Rebuilds the knowledge base from specifications and reference code securely.
- `build_vectordb.py`: Vectors and stores the corpus in ChromaDB.
- `benchmark_runner.py`: Executes the validation benchmarks across different ISA groupings.
- `rag_pipeline.py`: A playground/diagnostic tool for custom pipeline testing.
- `generated_rtl/`: Contains the consolidated, fully-verified RISC-V processor (`riscv_core.v`) and its simulation testbench (`testbench.sv`).

## ⚙️ Setup & Hardware Generation

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure Environment**:
   Rename `.env.example` to `.env` and add your `GROQ_API_KEY`. (Ensure `api.groq.com` is accessible on your network).
3. **Build the Database**:
   ```bash
   python build_corpus.py
   python build_vectordb.py
   ```
4. **Generate RTL**:
   ```bash
   python rag_pipeline.py
   ```

## 🧪 Simulation using EDA Playground

Because setting up C++ simulation environments (like Verilator) locally is prone to cross-platform compiler issues, this generated code is **100% compatible with EDA Playground**'s standard Verilog simulators.

1. Go to [EDA Playground](https://edaplayground.com/).
2. On the left side, select the simulator: **Icarus Verilog 0.10.0** (Check "Open EPWave after run").
3. Paste the contents of `generated_rtl/riscv_core.v` into the **design.sv** window.
4. Paste the contents of `generated_rtl/testbench.sv` into the **testbench.sv** window.
5. Click **Run**. 

You will see `ALL TESTS PASSED (11/11)` printed in the console and the waveform (EPWave) will open automatically!

---
**Author**: Utkarsh Nayan
**Date**: April 2026
