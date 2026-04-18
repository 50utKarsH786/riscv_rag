# RAG for RISC-V RTL — Submission


---

## Table of Contents
1. [Overview & Motivation](#1-overview--motivation)
2. [Corpus & Knowledge Base](#2-corpus--knowledge-base)
3. [Pipeline Design](#3-pipeline-design)
4. [Generated RTL](#4-generated-rtl)
5. [Simulation Results](#5-simulation-results)
6. [Failure Analysis & Self-Correction](#6-failure-analysis--self-correction)
7. [Reflection](#7-reflection)
8. [Appendix — Key Source Files](#8-appendix--key-source-files)

---

## 1. Overview & Motivation

Generating correct, synthesizable RTL for a processor is a fundamentally different challenge from generating application software. A missing stall, a blocking assignment in a clocked block, or an unsigned comparison where a signed one was required can all cause silent functional failures that are completely invisible until simulation. Standard LLMs, even capable ones, routinely produce plausible-looking Verilog that fails immediately under a linter or simulator.

This submission addresses that gap by building a Retrieval-Augmented Generation (RAG) pipeline specifically engineered for hardware correctness. The system:
- **Retrieves** the most semantically relevant RTL patterns and specification fragments before generating any code.
- **Enforces** a set of hard RTL rules through the system prompt, derived from observed first-pass failure modes.
- **Automatically verifies** every generated module against Verilator's structural linter and feeds errors back to the LLM for self-correction, up to a configurable number of retries.

The target design is a single-cycle RV32I processor implementing the full base integer instruction set. The core was generated using the RAG pipeline, iteratively corrected via the linter loop, and then validated on EDA Playground using Icarus Verilog with a custom SystemVerilog testbench covering 11 functional correctness checks spanning ALU operations, memory access, branch control flow, and jump instructions. All 11 tests passed.

---

## 2. Corpus & Knowledge Base

### 2.1 Sources
The corpus was deliberately narrow and high-quality. Each source was chosen because it either establishes ground truth (the spec), demonstrates correct idiomatic patterns (reference RTL), or actively documents the failure modes most likely to appear in LLM output (the bug library).

| Source | Category | Rationale |
|---|---|---|
| `riscv_spec/rv32i.md` | Specification | Hand-curated from the official unprivileged ISA spec. Covers all 47 RV32I instructions with encoding tables, immediate formats, and PC update rules. Ground truth for the generator. |
| `riscv_spec/decoder_logic.md` | Specification | A control-signal mapping table (opcode → ALUSrc, ALUOp, RegWrite, MemWrite, Branch). Helps the LLM disambiguate instructions that share funct3 values across opcodes. |
| `rtl_code/register_file.v` | Reference RTL | A clean, minimal RV32I register file. Demonstrates the `x0` hardwiring pattern and the separation of synchronous write from asynchronous read. |
| `rtl_code/alu.v` | Reference RTL | A complete 10-operation ALU using `localparam` constants and `$signed()` casts. Provides an idiomatic template the LLM can mirror directly. |
| `rtl_code/picorv32.v` | Reference RTL | Downloaded directly from the YosysHQ repository. A production-quality RV32IMC core used as a source of synthesizable Verilog patterns. |
| `rtl_code/serv_alu.v`, `serv_decode.v` | Reference RTL | From the SERV (Serial RISC-V) core. Demonstrates compact, area-efficient decode and ALU implementations. |
| `design_patterns/...` | Design Patterns | Templates for pipeline registers, FSMs, and decoders. |
| `bugs/common_rtl_bugs.md` | Bug Library | 12 documented RTL bugs with wrong and correct examples (blocking/non-blocking misuse, missing default, signed comparison errors, etc.). |

**Total corpus size:** ~14 files, approximately 120 KB of text and Verilog source.

### 2.2 Chunking Strategy
Chunking strategy was the first substantive design decision, and it diverges from standard NLP practice:
- **For Verilog files:** Each file was split at `module` boundaries to preserve semantic coherence.
- **For Markdown files:** Split at `##` header boundaries to keep an instruction's encoding, semantics, and example in a single chunk.
- **Chunk overlap:** None applied. Overlapping hardware descriptions produces nonsensical hybrid context.

### 2.3 Embedding Model
Used `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional dense vectors, stored in ChromaDB). Selected because it is fast, handles mixed code/text content acceptably, and is deterministic/local.

### 2.4 Retrieval Strategy
Dense retrieval only, Top-K = 5. No BM25 or hybrid retrieval was implemented in this iteration. Retrieving more context (K = 10) caused context pollution, while 5 chunks provided enough grounding without overwhelming the generation window.

---

## 3. Pipeline Design

### 3.1 Architecture
The architecture flows from natural language to structured prompt, through the Groq LLM, into a Verilog extractor, and finally into a Verilator linter self-correction loop. Verified files are then functionally tested on EDA Playground.

### 3.2 System Prompt Rules
Seven hard rules were embedded in every generation request:
1. Use non-blocking assignments (`<=`) in all clocked `always` blocks.
2. Use blocking assignments (`=`) only in combinational `always @(*)` blocks.
3. Always add `default` cases in all `case` statements.
4. `x0` register must always read as zero; writes to `x0` must be ignored.
5. All module ports must be explicitly typed.
6. For SRA use `$signed(a) >>> b[4:0]`; for SLT use `$signed(a) < $signed(b)`.
7. Generate ONLY Verilog code wrapped in ```verilog ... ``` tags.

### 3.3 Self-Correction Loop
The linter loop generates a candidate module, runs `verilator --lint-only -Wall`, and feeds any structured error messages (e.g., `%Warning-UNDRIVEN`) back to the LLM for self-healing.

### 3.4 Tools and Models
- **LLM**: `llama-3.3-70b-versatile` via Groq
- **Embedding**: `all-MiniLM-L6-v2`
- **Vector Store**: ChromaDB
- **Structural Linter**: Verilator
- **Functional Simulator**: EDA Playground (Icarus Verilog)

---

## 4. Generated RTL

### 4.1 Final Output: `riscv_core.v`
The final file is a single-module, single-cycle RV32I processor. Key structural decisions include fully combinational PC logic, asynchronous read/synchronous write register file, and correct `$signed()` casts for ALU operations.

### 4.2 Example Trace: ALU Generation
- **Prompt**: Generate a complete RV32I ALU Verilog module supporting all 10 operations...
- **Retrieval**: Pulled reference ALU, R-type spec, and bug library chunks for signed comparisons.
- **Result**: Passed Verilator linting on Attempt 1.

### 4.3 Example Trace: Load/Store Unit
- **Prompt**: Generate a Verilog load/store unit...
- **Issue**: Attempt 1 generated a width mismatch for the `SB` instruction data bus.
- **Correction**: Verilator flagged `%Warning-WIDTH`. The LLM applied the replication operator correctly (`{4{rs2_data[7:0]}}`) on Attempt 2.

---

## 5. Simulation Results

### 5.1 Setup
Functional verification was performed on EDA Playground using Icarus Verilog. Both Instruction and Data memories respond combinationally, matching the single-cycle core's assumptions.

### 5.2 Assertion Results (11/11 PASS)
The custom testbench executed a holistic 14-instruction RV32I program covering fundamental operations:
- **I-type arithmetic** (ADDI) — PASS
- **R-type arithmetic** (ADD, SUB) — PASS
- **Logical operations** (AND, OR, XOR) — PASS
- **Branch logic** (BEQ taken/not taken) — PASS
- **Memory operations** (LW, SW) — PASS
- **Upper Immediates** (LUI, AUIPC) — PASS

The critical test was a `BEQ` that skips a fail sentinel, testing the branch comparator, immediate sign extension, and PC adder simultaneously. All tests passed.

---

## 6. Failure Analysis & Self-Correction

- **Blocking Assignments in Sequential Blocks**: Initially occurred frequently. Resolved by embedding Rule 1 and 2 in the system prompt.
- **Missing `default` in `case` Statements**: Caused `%Warning-CASEINCOMPLETE` (latch inference). Resolved effectively by the Verilator self-correction loop adding the missing default branch.
- **Store Data Bus Width Mismatch**: The LLM wrote `store_data = rs2_data[7:0]` instead of the 32-bit replication pattern. Verilator flagged it, and the LLM fixed it in one iteration.

---

## 7. Reflection

### 7.1 What Was the Hardest Part?
The hardest part was understanding the boundary between what the linter can catch and what only simulation can reveal. Verilator's `--lint-only` mode is blind to functional errors (e.g. using `>` instead of `>=` for BGE). Closing that gap requires full simulation inside the correction loop.

### 7.2 What Would I Do Differently?
- **Simulation in the correction loop**: Use micro-tests during generation.
- **Code-aware chunking**: Annotate sub-module structures with their parent module name rather than treating files as atomic block chunks.
- **Temperature annealing**: Raise the LLM temperature on later retries to encourage structural exploration if pattern matching fails.

### 7.3 Limits of RAG for Hardware Generation
RAG substantially improves first-pass quality by grounding the LLM in verified patterns. However, it has a hard ceiling determined by the verifier. It is most useful as a drafting accelerator, producing structurally sound Verilog that still requires formal verification by a human engineer.

---

## 8. Appendix — Key Source Files

| File | Description |
|---|---|
| `riscv_core.v` | Final generated single-cycle RV32I processor (EDA Playground compatible) |
| `testbench.sv` | EDA Playground testbench with 11 functional assertion checks |
| `riscv_rag_engine.py` | Core RAG engine handling retrieval, generation, and linting loop |
| `rag_pipeline.py` | CLI entry point |
| `build_corpus.py` | Corpus construction script |
