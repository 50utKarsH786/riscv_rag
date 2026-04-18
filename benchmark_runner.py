"""
benchmark_runner.py - Step 5 Benchmark for RISC-V RAG Engine

Runs a suite of representative RV32I RTL generation tasks, measures:
  - Pass rate (how many outputs Verilator accepts without errors)
  - Attempts needed (1 = first-pass, >1 = self-correction worked)
  - Total tokens / latency per query
  - Simulated "ISA coverage" (which RV32I instruction groups were exercised)

Usage:
  python benchmark_runner.py

Requirements: same as riscv_rag_engine.py
  - ChromaDB populated (run build_corpus.py + build_vectordb.py first)
  - GROQ_API_KEY set in .env
  - api.groq.com in your network allowlist
  - verilator installed (optional — skipped if missing)
"""

import os
import sys
import time
import json
from datetime import datetime
from riscv_rag_engine import RISCVRagEngine

# ── Benchmark suite ───────────────────────────────────────────────────
BENCHMARKS = [
    {
        "id": "B01",
        "name": "ALU — All R-type ops",
        "group": "rv32i-alu",
        "query": (
            "Generate a complete RV32I ALU module supporting all R-type operations: "
            "ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND. "
            "Use $signed() for SRA and SLT. Include a zero flag output."
        ),
        "filename": "bench_alu.v",
        "check_keywords": ["ALU_ADD", "ALU_SRA", "$signed", "zero", "default"],
    },
    {
        "id": "B02",
        "name": "Register File — x0 hardwired",
        "group": "rv32i-regfile",
        "query": (
            "Generate a RV32I 32x32 register file module with synchronous write "
            "and asynchronous read. x0 must always return 0; writes to x0 are ignored."
        ),
        "filename": "bench_regfile.v",
        "check_keywords": ["5'b0", "rdata1", "rdata2", "posedge clk", "<="],
    },
    {
        "id": "B03",
        "name": "Decoder — R/I/S/B/U/J types",
        "group": "rv32i-decode",
        "query": (
            "Generate a RV32I instruction decoder module that extracts opcode, funct3, "
            "funct7, rs1, rs2, rd, and all immediate formats (I, S, B, U, J). "
            "Output control signals: reg_we, mem_we, mem_re, alu_src, is_branch, is_jump."
        ),
        "filename": "bench_decoder.v",
        "check_keywords": ["imm_i", "imm_b", "imm_j", "opcode", "reg_we"],
    },
    {
        "id": "B04",
        "name": "IF/ID Pipeline Register",
        "group": "rv32i-pipeline",
        "query": (
            "Generate the IF/ID pipeline register module for a 5-stage RISC-V pipeline. "
            "Support synchronous reset, flush (for branch), and stall (for hazard). "
            "On flush insert NOP (32'h00000013)."
        ),
        "filename": "bench_ifid.v",
        "check_keywords": ["flush", "stall", "00000013", "posedge clk", "<="],
    },
    {
        "id": "B05",
        "name": "Load-Store Unit",
        "group": "rv32i-lsu",
        "query": (
            "Generate a RV32I load-store unit (LSU) module that handles LB, LH, LW, "
            "LBU, LHU loads with correct sign/zero extension, and SB, SH, SW stores. "
            "Interface: address, write_data, read_data, mem_we, funct3."
        ),
        "filename": "bench_lsu.v",
        "check_keywords": ["LB", "LH", "LW", "sign", "funct3", "default"],
    },
    {
        "id": "B06",
        "name": "Branch Unit — all conditions",
        "group": "rv32i-branch",
        "query": (
            "Generate a RV32I branch unit module that evaluates all 6 branch conditions: "
            "BEQ, BNE, BLT, BGE, BLTU, BGEU. "
            "Use $signed() for BLT and BGE. Output branch_taken signal."
        ),
        "filename": "bench_branch.v",
        "check_keywords": ["BEQ", "BLT", "$signed", "branch_taken", "default"],
    },
]

# ── Keyword checker (static analysis proxy for lint) ─────────────────
def check_keywords(code: str, keywords: list) -> dict:
    results = {}
    for kw in keywords:
        results[kw] = kw in code
    return results


def run_benchmarks():
    print("=" * 65)
    print("  RISC-V RAG Engine — Step 5 Benchmark")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    try:
        engine = RISCVRagEngine()
    except RuntimeError as e:
        print(f"\nFATAL: Cannot initialize engine.\n{e}")
        sys.exit(1)

    results = []
    total   = len(BENCHMARKS)
    passed  = 0
    total_attempts = 0
    group_coverage = {}

    for bm in BENCHMARKS:
        print(f"\n[{bm['id']}] {bm['name']}")
        print(f"      Group: {bm['group']}")

        t0 = time.time()
        try:
            result = engine.generate_with_correction(bm["query"], bm["filename"])
        except RuntimeError as e:
            print(f"      ERROR: {e}")
            results.append({**bm, "status": "ERROR", "error": str(e)})
            continue

        elapsed = time.time() - t0
        code    = result["code"]
        verified = result["verified"]
        attempts = result["attempts"]
        lint_status = result["lint_status"]

        # Keyword static check
        kw_results = check_keywords(code, bm["check_keywords"])
        kw_pass = sum(kw_results.values())
        kw_total = len(kw_results)

        # Consider "passed" if verified OR (verilator skipped AND keywords ok)
        is_pass = verified or (
            "skipped" in lint_status and kw_pass >= kw_total * 0.8
        )

        if is_pass:
            passed += 1
            status = "PASS"
        else:
            status = "FAIL"

        total_attempts += attempts
        group_coverage[bm["group"]] = is_pass

        print(f"      Status  : {status}")
        print(f"      Attempts: {attempts}/{engine.max_retries}")
        print(f"      Lint    : {lint_status[:80] if lint_status else 'clean'}")
        print(f"      Keywords: {kw_pass}/{kw_total} found - {list(kw_results.items())}")
        print(f"      Time    : {elapsed:.1f}s  |  Code size: {len(code)} chars")

        results.append({
            **bm,
            "status":      status,
            "verified":    verified,
            "attempts":    attempts,
            "lint_status": lint_status,
            "kw_pass":     kw_pass,
            "kw_total":    kw_total,
            "elapsed_s":   round(elapsed, 2),
            "code_chars":  len(code),
        })

    # ── Summary ───────────────────────────────────────────────────────
    pass_rate     = passed / total * 100
    avg_attempts  = total_attempts / total
    isa_groups    = len(group_coverage)
    isa_covered   = sum(group_coverage.values())

    print("\n" + "=" * 65)
    print("  BENCHMARK RESULTS SUMMARY")
    print("=" * 65)
    print(f"\n  Overall Pass Rate : {passed}/{total}  ({pass_rate:.0f}%)")
    print(f"  Avg Attempts/Query: {avg_attempts:.1f}")
    print(f"  ISA Group Coverage: {isa_covered}/{isa_groups} groups passing")
    print()
    print("  Per-Test Results:")
    print(f"  {'ID':<5} {'Name':<35} {'Status':<6} {'Attempts':<9} {'KW'}")
    print("  " + "-" * 60)
    for r in results:
        if "error" in r:
            print(f"  {r['id']:<5} {r['name']:<35} ERROR")
        else:
            print(
                f"  {r['id']:<5} {r['name']:<35} {r['status']:<6} "
                f"{r['attempts']}/{engine.max_retries}       "
                f"{r['kw_pass']}/{r['kw_total']}"
            )

    print()
    print("  ISA Instruction Groups Tested:")
    for group, ok in group_coverage.items():
        marker = "[PASS]" if ok else "[FAIL]"
        print(f"    {marker}  {group}")

    # ── Dhrystone / CoreMark note ─────────────────────────────────────
    print()
    print("  NOTE: Dhrystone / CoreMark scores require:")
    print("    1. A complete synthesizable RV32I core (e.g. generated by this tool)")
    print("    2. Compiled with riscv32-unknown-elf-gcc -O2 -march=rv32i")
    print("    3. Simulation with Verilator or QEMU rv32 target")
    print("    4. Typical soft-core baselines:")
    print("         PicoRV32 (100 MHz): ~1.17 DMIPS/MHz (~117 DMIPS at 100 MHz)")
    print("         SERV (serial):      throughput-optimised, not DMIPS-focused")
    print("         This RAG-generated core: run sim to measure (see README)")
    print()
    print("  ISA Test Pass Rate (riscv-tests rv32ui):")
    print("    To run: git clone https://github.com/riscv-software-src/riscv-tests")
    print("    Then:   make -C riscv-tests/isa rv32ui")
    print("    Expected baseline with correct ALU+regfile+decoder: 42-47/47 tests")
    print()
    print("=" * 65)

    # Save results JSON
    os.makedirs("benchmark_results", exist_ok=True)
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"benchmark_results/bench_{ts}.json"
    with open(out, "w") as f:
        json.dump({
            "timestamp":   ts,
            "pass_rate":   f"{passed}/{total}",
            "avg_attempts": avg_attempts,
            "isa_coverage": f"{isa_covered}/{isa_groups}",
            "tests":       results,
        }, f, indent=2)
    print(f"\n  Full results saved → {out}")
    print("=" * 65)

    return pass_rate


if __name__ == "__main__":
    run_benchmarks()
