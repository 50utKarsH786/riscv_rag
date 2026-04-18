"""
build_corpus.py — Fixed version
Changes vs original:
  - github.com / raw.githubusercontent.com may be blocked; graceful stub fallback
  - serv_alu.v / serv_decode.v / picorv32.v get minimal stubs if download fails
    so build_vectordb.py still runs and produces a usable (if smaller) DB
"""
import os
import requests

# ── Create directories ────────────────────────────────────────────────
for d in ["corpus/riscv_spec", "corpus/rtl_code", "corpus/design_patterns",
          "corpus/bugs", "corpus/meta"]:
    os.makedirs(d, exist_ok=True)

# ── meta ──────────────────────────────────────────────────────────────
print("Writing meta/choice_documentation.md...")
with open("corpus/meta/choice_documentation.md", "w", encoding="utf-8") as f:
    f.write("""# RAG Corpus Construction Choices

## What was included and why:
1. **Official RV32I Spec**: Essential for ground-truth instruction semantics and encoding.
2. **Reference RTL (SERV, PicoRV32)**: Provides "gold standard" Verilog patterns.
3. **Design Patterns**: Curated templates for FSMs and pipeline registers.
4. **Common Bug Documentation**: Targets LLM weaknesses (blocking assignments, etc.).

## Chunking Strategy:
- **Verilog**: Split by `module` boundaries.
- **Specs/Markdown**: Split by `##` headers.
""")

# ── riscv_spec/rv32i.md ───────────────────────────────────────────────
print("Writing riscv_spec/rv32i.md...")
with open("corpus/riscv_spec/rv32i.md", "w", encoding="utf-8") as f:
    f.write("""# RV32I Base Integer Instruction Set — Complete Reference

## Instruction Encoding Formats
- R: funct7[31:25] | rs2[24:20] | rs1[19:15] | funct3[14:12] | rd[11:7]  | opcode[6:0]
- I: imm[31:20]   | rs1[19:15] | funct3[14:12] | rd[11:7]    | opcode[6:0]
- S: imm[31:25]   | rs2[24:20] | rs1[19:15]  | funct3[14:12] | imm[11:7] | opcode[6:0]
- B: imm[12,10:5] | rs2[24:20] | rs1[19:15]  | funct3[14:12] | imm[4:1,11]| opcode[6:0]
- U: imm[31:12]   | rd[11:7]   | opcode[6:0]
- J: imm[20,10:1,11,19:12] | rd[11:7] | opcode[6:0]

## R-type Instructions (opcode=0110011)
ADD:  funct3=000 funct7=0000000  rd = rs1 + rs2
SUB:  funct3=000 funct7=0100000  rd = rs1 - rs2
SLL:  funct3=001 funct7=0000000  rd = rs1 << rs2[4:0]
SLT:  funct3=010 funct7=0000000  rd = ($signed(rs1) < $signed(rs2)) ? 1 : 0
SLTU: funct3=011 funct7=0000000  rd = (rs1 < rs2) ? 1 : 0
XOR:  funct3=100 funct7=0000000  rd = rs1 ^ rs2
SRL:  funct3=101 funct7=0000000  rd = rs1 >> rs2[4:0]
SRA:  funct3=101 funct7=0100000  rd = $signed(rs1) >>> rs2[4:0]
OR:   funct3=110 funct7=0000000  rd = rs1 | rs2
AND:  funct3=111 funct7=0000000  rd = rs1 & rs2

## I-type Arithmetic (opcode=0010011)
ADDI:  funct3=000  rd = rs1 + sign_ext(imm)
SLTI:  funct3=010  rd = ($signed(rs1) < $signed(imm)) ? 1 : 0
SLTIU: funct3=011  rd = (rs1 < imm) ? 1 : 0
XORI:  funct3=100  rd = rs1 ^ sign_ext(imm)
ORI:   funct3=110  rd = rs1 | sign_ext(imm)
ANDI:  funct3=111  rd = rs1 & sign_ext(imm)
SLLI:  funct3=001 imm[11:5]=0000000  rd = rs1 << imm[4:0]
SRLI:  funct3=101 imm[11:5]=0000000  rd = rs1 >> imm[4:0]
SRAI:  funct3=101 imm[11:5]=0100000  rd = $signed(rs1) >>> imm[4:0]

## Load Instructions (opcode=0000011)
LB:  funct3=000  rd = sign_ext(mem8[rs1+imm])
LH:  funct3=001  rd = sign_ext(mem16[rs1+imm])
LW:  funct3=010  rd = mem32[rs1+imm]
LBU: funct3=100  rd = zero_ext(mem8[rs1+imm])
LHU: funct3=101  rd = zero_ext(mem16[rs1+imm])

## Store Instructions (opcode=0100011)
SB: funct3=000  mem8[rs1+imm]  = rs2[7:0]
SH: funct3=001  mem16[rs1+imm] = rs2[15:0]
SW: funct3=010  mem32[rs1+imm] = rs2[31:0]

## Branch Instructions (opcode=1100011)
BEQ:  funct3=000  if rs1 == rs2: pc += imm_b
BNE:  funct3=001  if rs1 != rs2: pc += imm_b
BLT:  funct3=100  if $signed(rs1) <  $signed(rs2): pc += imm_b
BGE:  funct3=101  if $signed(rs1) >= $signed(rs2): pc += imm_b
BLTU: funct3=110  if rs1 <  rs2: pc += imm_b
BGEU: funct3=111  if rs1 >= rs2: pc += imm_b

## Jump Instructions
JAL  (opcode=1101111): rd = pc+4; pc = pc + imm_j
JALR (opcode=1100111): rd = pc+4; pc = (rs1+imm_i) & ~1

## Upper Immediate
LUI   (opcode=0110111): rd = imm_u
AUIPC (opcode=0010111): rd = pc + imm_u

## System (opcode=1110011)
ECALL  EBREAK

## ABI Register Conventions
x0  zero  hardwired 0 (reads=0, writes ignored)
x1  ra    x2  sp    x3  gp    x4  tp
x5-x7 t0-t2  x8 s0/fp  x9 s1  x10-x11 a0-a1
x12-x17 a2-a7  x18-x27 s2-s11  x28-x31 t3-t6
""")

# ── riscv_spec/decoder_logic.md ───────────────────────────────────────
print("Writing riscv_spec/decoder_logic.md...")
with open("corpus/riscv_spec/decoder_logic.md", "w", encoding="utf-8") as f:
    f.write("""# RISC-V Decoder Mapping Table

| Instruction | Opcode  | Funct3 | Funct7  | ALUSrc | ALUOp | RegWrite | MemWrite | Branch |
|-------------|---------|--------|---------|--------|-------|----------|----------|--------|
| ADD         | 0110011 | 000    | 0000000 | 0      | ADD   | 1        | 0        | 0      |
| SUB         | 0110011 | 000    | 0100000 | 0      | SUB   | 1        | 0        | 0      |
| ADDI        | 0010011 | 000    | -       | 1      | ADD   | 1        | 0        | 0      |
| LW          | 0000011 | 010    | -       | 1      | ADD   | 1        | 0        | 0      |
| SW          | 0100011 | 010    | -       | 1      | ADD   | 0        | 1        | 0      |
| BEQ         | 1100011 | 000    | -       | 0      | SUB   | 0        | 0        | 1      |

## Common Decoder Pitfalls
- XORI vs XOR: different opcodes (0010011 vs 0110011), same funct3.
- LUI/AUIPC: do not use rs1/rs2; result comes directly from U-type immediate.
""")

# ── rtl_code/register_file.v ──────────────────────────────────────────
print("Writing rtl_code/register_file.v...")
with open("corpus/rtl_code/register_file.v", "w", encoding="utf-8") as f:
    f.write("""\
// RV32I Register File — 32x32-bit, x0 hardwired to zero
// Synchronous write, asynchronous read
module register_file (
    input  wire        clk,
    input  wire        we,
    input  wire [4:0]  rs1,
    input  wire [4:0]  rs2,
    input  wire [4:0]  rd,
    input  wire [31:0] wdata,
    output wire [31:0] rdata1,
    output wire [31:0] rdata2
);
    reg [31:0] regs [1:31];

    assign rdata1 = (rs1 == 5'b0) ? 32'b0 : regs[rs1];
    assign rdata2 = (rs2 == 5'b0) ? 32'b0 : regs[rs2];

    always @(posedge clk) begin
        if (we && rd != 5'b0)
            regs[rd] <= wdata;
    end
endmodule
""")

# ── rtl_code/alu.v ────────────────────────────────────────────────────
print("Writing rtl_code/alu.v...")
with open("corpus/rtl_code/alu.v", "w", encoding="utf-8") as f:
    f.write("""\
// RV32I ALU — all RV32I arithmetic/logic operations
module alu (
    input  wire [31:0] a,
    input  wire [31:0] b,
    input  wire [3:0]  alu_op,
    output reg  [31:0] result,
    output wire        zero
);
    localparam ALU_ADD  = 4'b0000;
    localparam ALU_SUB  = 4'b0001;
    localparam ALU_AND  = 4'b0010;
    localparam ALU_OR   = 4'b0011;
    localparam ALU_XOR  = 4'b0100;
    localparam ALU_SLL  = 4'b0101;
    localparam ALU_SRL  = 4'b0110;
    localparam ALU_SRA  = 4'b0111;
    localparam ALU_SLT  = 4'b1000;
    localparam ALU_SLTU = 4'b1001;

    assign zero = (result == 32'b0);

    always @(*) begin
        case (alu_op)
            ALU_ADD:  result = a + b;
            ALU_SUB:  result = a - b;
            ALU_AND:  result = a & b;
            ALU_OR:   result = a | b;
            ALU_XOR:  result = a ^ b;
            ALU_SLL:  result = a << b[4:0];
            ALU_SRL:  result = a >> b[4:0];
            // FIX: use $signed() for arithmetic right shift
            ALU_SRA:  result = $signed(a) >>> b[4:0];
            // FIX: use $signed() for signed comparison
            ALU_SLT:  result = ($signed(a) < $signed(b)) ? 32'b1 : 32'b0;
            ALU_SLTU: result = (a < b) ? 32'b1 : 32'b0;
            default:  result = 32'b0;
        endcase
    end
endmodule
""")

# ── Download helpers (github.com allowed) ─────────────────────────────
def download_or_stub(url: str, dest: str, stub: str) -> None:
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        with open(dest, "w", encoding="utf-8") as f:
            f.write(r.text)
        print(f"  Saved {os.path.basename(dest)} ({len(r.text)} chars)")
    except Exception as e:
        print(f"  Download failed ({e}); writing stub.")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(stub)

# picorv32.v
print("Downloading picorv32.v...")
download_or_stub(
    "https://raw.githubusercontent.com/YosysHQ/picorv32/master/picorv32.v",
    "corpus/rtl_code/picorv32.v",
    "// picorv32.v unavailable (network blocked). Stub placeholder.\n"
    "// See https://github.com/YosysHQ/picorv32\n"
)

# serv files
for fname, url in {
    "serv_alu.v":    "https://raw.githubusercontent.com/olofk/serv/main/rtl/serv_alu.v",
    "serv_decode.v": "https://raw.githubusercontent.com/olofk/serv/main/rtl/serv_decode.v",
}.items():
    print(f"Downloading {fname}...")
    download_or_stub(
        url,
        f"corpus/rtl_code/{fname}",
        f"// {fname} unavailable (network blocked). Stub placeholder.\n"
        f"// See https://github.com/olofk/serv\n"
    )

# ── design_patterns/pipeline.md ───────────────────────────────────────
print("Writing design_patterns/pipeline.md...")
with open("corpus/design_patterns/pipeline.md", "w", encoding="utf-8") as f:
    f.write("""# Pipeline Register Patterns for RISC-V

## 5-Stage Pipeline Overview
Fetch -> Decode -> Execute -> Memory -> Writeback

## IF/ID Pipeline Register
```verilog
always @(posedge clk or posedge rst) begin
    if (rst || flush_if) begin
        id_pc    <= 32'b0;
        id_instr <= 32'h00000013; // NOP
        id_valid <= 1'b0;
    end else if (!stall_if) begin
        id_pc    <= if_pc;
        id_instr <= if_instr;
        id_valid <= 1'b1;
    end
end
```

## ID/EX Pipeline Register
```verilog
always @(posedge clk or posedge rst) begin
    if (rst || flush_id) begin
        ex_pc <= 32'b0; ex_rs1_data <= 32'b0; ex_rs2_data <= 32'b0;
        ex_rd <= 5'b0;  ex_alu_op   <= 4'b0;  ex_alu_src  <= 1'b0;
        ex_mem_we <= 1'b0; ex_reg_we <= 1'b0; ex_valid <= 1'b0;
    end else if (!stall_id) begin
        ex_pc <= id_pc; ex_rs1_data <= id_rs1_data; ex_rs2_data <= id_rs2_data;
        ex_rd <= id_rd; ex_alu_op   <= id_alu_op;   ex_alu_src  <= id_alu_src;
        ex_mem_we <= id_mem_we; ex_reg_we <= id_reg_we; ex_valid <= id_valid;
    end
end
```

## Hazard Detection
```verilog
assign load_use_hazard = ex_mem_load && (ex_rd != 0) &&
                         ((ex_rd == id_rs1) || (ex_rd == id_rs2));
assign flush_if = branch_taken;
assign flush_id = branch_taken;
assign stall_if = load_use_hazard;
assign stall_id = load_use_hazard;
assign flush_ex = load_use_hazard;
```
""")

# ── design_patterns/fsm.md ────────────────────────────────────────────
print("Writing design_patterns/fsm.md...")
with open("corpus/design_patterns/fsm.md", "w", encoding="utf-8") as f:
    f.write("""# FSM Design Patterns for RTL

## Two-Always FSM (Recommended)
```verilog
localparam IDLE=3'd0, FETCH=3'd1, DECODE=3'd2,
           EXECUTE=3'd3, MEMORY=3'd4, WRITEBACK=3'd5;
reg [2:0] state, next_state;

always @(posedge clk or posedge rst) begin
    if (rst) state <= IDLE;
    else     state <= next_state;
end

always @(*) begin
    case (state)
        IDLE:      next_state = FETCH;
        FETCH:     next_state = mem_ready ? DECODE : FETCH;
        DECODE:    next_state = EXECUTE;
        EXECUTE:   next_state = (is_load||is_store) ? MEMORY : WRITEBACK;
        MEMORY:    next_state = mem_ready ? WRITEBACK : MEMORY;
        WRITEBACK: next_state = FETCH;
        default:   next_state = IDLE;
    endcase
end
```
""")

# ── design_patterns/decoder.md ────────────────────────────────────────
print("Writing design_patterns/decoder.md...")
with open("corpus/design_patterns/decoder.md", "w", encoding="utf-8") as f:
    f.write("""# Instruction Decoder Design Pattern for RV32I

## Field Extraction
```verilog
wire [6:0] opcode = instr[6:0];
wire [4:0] rd     = instr[11:7];
wire [2:0] funct3 = instr[14:12];
wire [4:0] rs1    = instr[19:15];
wire [4:0] rs2    = instr[24:20];
wire [6:0] funct7 = instr[31:25];
```

## Immediate Decoding
```verilog
wire [31:0] imm_i = {{20{instr[31]}}, instr[31:20]};
wire [31:0] imm_s = {{20{instr[31]}}, instr[31:25], instr[11:7]};
wire [31:0] imm_b = {{19{instr[31]}}, instr[31], instr[7], instr[30:25], instr[11:8], 1'b0};
wire [31:0] imm_u = {instr[31:12], 12'b0};
wire [31:0] imm_j = {{11{instr[31]}}, instr[31], instr[19:12], instr[20], instr[30:21], 1'b0};
```

## Opcode Definitions
```verilog
localparam OP_LUI=7'b0110111, OP_AUIPC=7'b0010111, OP_JAL=7'b1101111;
localparam OP_JALR=7'b1100111, OP_BRANCH=7'b1100011, OP_LOAD=7'b0000011;
localparam OP_STORE=7'b0100011, OP_ALUI=7'b0010011, OP_ALUR=7'b0110011;
localparam OP_SYSTEM=7'b1110011;
```
""")

# ── bugs/common_rtl_bugs.md ───────────────────────────────────────────
print("Writing bugs/common_rtl_bugs.md...")
with open("corpus/bugs/common_rtl_bugs.md", "w", encoding="utf-8") as f:
    f.write("""# Common RTL Bugs in RISC-V Processor Design

## BUG 1: Blocking vs Non-blocking Assignments
WRONG:  always @(posedge clk) begin a = b; end
CORRECT: always @(posedge clk) begin a <= b; end
RULE: Use <= in clocked blocks. Use = in combinational (always @(*)).

## BUG 2: Missing Default in Case Statement
WRONG: case(op) 2'b00: out=a; 2'b01: out=b; endcase  // latch inferred
CORRECT: add: default: out = 32'b0;

## BUG 3: x0 Not Hardwired to Zero
CORRECT:
  assign rdata1 = (rs1==5'b0) ? 32'b0 : regs[rs1];
  always @(posedge clk) if (we && rd!=5'b0) regs[rd] <= wdata;

## BUG 4: Wrong Branch Offset
CORRECT: pc_next = pc + imm_b;  // imm_b is signed byte offset, LSB=0

## BUG 5: JALR Not Clearing Bit 0
CORRECT: pc_next = (rs1_data + imm_i) & 32'hFFFFFFFE;

## BUG 6: Load Sign Extension Missing
LB:  rd = {{24{mem_data[7]}},  mem_data[7:0]};
LH:  rd = {{16{mem_data[15]}}, mem_data[15:0]};
LBU: rd = {24'b0, mem_data[7:0]};
LHU: rd = {16'b0, mem_data[15:0]};

## BUG 7: Pipeline Not Flushed on Branch
assign flush_if = branch_taken;
assign flush_id = branch_taken;

## BUG 8: Incomplete Sensitivity List
CORRECT: always @(*) instead of named signals.

## BUG 9: Signed vs Unsigned Comparison
SLT:  result = ($signed(rs1) < $signed(rs2)) ? 32'b1 : 32'b0;
SLTU: result = (rs1 < rs2) ? 32'b1 : 32'b0;

## BUG 10: Load-Use Hazard
load_use_hazard = ex_is_load && (ex_rd!=0) &&
                  ((ex_rd==id_rs1)||(ex_rd==id_rs2));

## BUG 11: PC Not Initialized
always @(posedge clk or posedge rst) begin
    if (rst) pc <= 32'h00000000;
    else     pc <= pc_next;
end

## BUG 12: SRA Using Logical Shift
WRONG:  result = a >> b[4:0];
CORRECT: result = $signed(a) >>> b[4:0];
""")

print("\Corpus build complete! Structure:")
for root, dirs, files in os.walk("corpus"):
    level = root.replace("corpus", "").count(os.sep)
    indent = "  " * level
    print(f"{indent}{os.path.basename(root)}/")
    for fname in files:
        fpath = os.path.join(root, fname)
        print(f"{indent}  {fname} ({os.path.getsize(fpath)} bytes)")
