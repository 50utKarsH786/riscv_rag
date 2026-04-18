// RV32I Single-Cycle Core - EDA Playground Compatible
// Fixed: reg declarations, signed casts, replication operators
`timescale 1ns/1ps

module riscv_core (
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] imem_rdata,
    output wire [31:0] imem_addr,
    output wire        mem_we,
    output wire [3:0]  mem_be,
    output wire [31:0] dmem_addr,
    output wire [31:0] dmem_wdata,
    input  wire [31:0] dmem_rdata
);

    // ── PC ────────────────────────────────────────────────────────
    reg [31:0] pc;
    assign imem_addr = pc;

    // ── Instruction fields ────────────────────────────────────────
    wire [6:0] opcode = imem_rdata[6:0];
    wire [4:0] rd     = imem_rdata[11:7];
    wire [2:0] funct3 = imem_rdata[14:12];
    wire [4:0] rs1    = imem_rdata[19:15];
    wire [4:0] rs2    = imem_rdata[24:20];
    wire [6:0] funct7 = imem_rdata[31:25];

    // ── Immediates ────────────────────────────────────────────────
    wire [31:0] imm_i = {{20{imem_rdata[31]}}, imem_rdata[31:20]};
    wire [31:0] imm_s = {{20{imem_rdata[31]}}, imem_rdata[31:25], imem_rdata[11:7]};
    wire [31:0] imm_b = {{19{imem_rdata[31]}}, imem_rdata[31], imem_rdata[7],
                          imem_rdata[30:25], imem_rdata[11:8], 1'b0};
    wire [31:0] imm_u = {imem_rdata[31:12], 12'b0};
    wire [31:0] imm_j = {{11{imem_rdata[31]}}, imem_rdata[31], imem_rdata[19:12],
                          imem_rdata[20], imem_rdata[30:21], 1'b0};

    // ── Opcode parameters ─────────────────────────────────────────
    localparam OP_LUI    = 7'b0110111;
    localparam OP_AUIPC  = 7'b0010111;
    localparam OP_JAL    = 7'b1101111;
    localparam OP_JALR   = 7'b1100111;
    localparam OP_BRANCH = 7'b1100011;
    localparam OP_LOAD   = 7'b0000011;
    localparam OP_STORE  = 7'b0100011;
    localparam OP_ALUI   = 7'b0010011;
    localparam OP_ALUR   = 7'b0110011;

    // ── Control signals ───────────────────────────────────────────
    reg        reg_we;
    reg        mem_we_r;
    reg        mem_re;
    reg        alu_src;
    reg [3:0]  alu_op;
    reg [31:0] imm_sel;

    always @(*) begin
        reg_we   = 1'b0;
        mem_we_r = 1'b0;
        mem_re   = 1'b0;
        alu_src  = 1'b0;
        alu_op   = 4'd0;
        imm_sel  = imm_i;

        case (opcode)
            OP_ALUR: begin
                reg_we  = 1'b1;
                alu_src = 1'b0;
                case ({funct7[5], funct3})
                    4'b0_000: alu_op = 4'd0; // ADD
                    4'b1_000: alu_op = 4'd1; // SUB
                    4'b0_111: alu_op = 4'd2; // AND
                    4'b0_110: alu_op = 4'd3; // OR
                    4'b0_100: alu_op = 4'd4; // XOR
                    4'b0_001: alu_op = 4'd5; // SLL
                    4'b0_101: alu_op = 4'd6; // SRL
                    4'b1_101: alu_op = 4'd7; // SRA
                    4'b0_010: alu_op = 4'd8; // SLT
                    4'b0_011: alu_op = 4'd9; // SLTU
                    default:  alu_op = 4'd0;
                endcase
            end

            OP_ALUI: begin
                reg_we  = 1'b1;
                alu_src = 1'b1;
                imm_sel = imm_i;
                case (funct3)
                    3'b000: alu_op = 4'd0; // ADDI
                    3'b111: alu_op = 4'd2; // ANDI
                    3'b110: alu_op = 4'd3; // ORI
                    3'b100: alu_op = 4'd4; // XORI
                    3'b001: alu_op = 4'd5; // SLLI
                    3'b101: alu_op = funct7[5] ? 4'd7 : 4'd6; // SRAI / SRLI
                    3'b010: alu_op = 4'd8; // SLTI
                    3'b011: alu_op = 4'd9; // SLTIU
                    default: alu_op = 4'd0;
                endcase
            end

            OP_LOAD:  begin reg_we=1'b1; alu_src=1'b1; mem_re=1'b1; imm_sel=imm_i; alu_op=4'd0; end
            OP_STORE: begin mem_we_r=1'b1; alu_src=1'b1; imm_sel=imm_s; alu_op=4'd0; end
            OP_BRANCH:begin alu_src=1'b0; imm_sel=imm_b; alu_op=4'd1; end
            OP_LUI:   begin reg_we=1'b1; imm_sel=imm_u; end
            OP_AUIPC: begin reg_we=1'b1; imm_sel=imm_u; alu_op=4'd0; end
            OP_JAL:   begin reg_we=1'b1; imm_sel=imm_j; end
            OP_JALR:  begin reg_we=1'b1; alu_src=1'b1; imm_sel=imm_i; alu_op=4'd0; end
            default:  begin end
        endcase
    end

    // ── Register File ─────────────────────────────────────────────
    reg  [31:0] regs [0:31];   // full 32 entries; x0 handled in read/write logic
    wire [31:0] rs1_data = (rs1 == 5'b0) ? 32'b0 : regs[rs1];
    wire [31:0] rs2_data = (rs2 == 5'b0) ? 32'b0 : regs[rs2];

    // ── ALU ───────────────────────────────────────────────────────
    wire [31:0] alu_a = (opcode == OP_AUIPC) ? pc : rs1_data;
    wire [31:0] alu_b = alu_src ? imm_sel : rs2_data;
    reg  [31:0] alu_result;

    always @(*) begin
        case (alu_op)
            4'd0: alu_result = alu_a + alu_b;
            4'd1: alu_result = alu_a - alu_b;
            4'd2: alu_result = alu_a & alu_b;
            4'd3: alu_result = alu_a | alu_b;
            4'd4: alu_result = alu_a ^ alu_b;
            4'd5: alu_result = alu_a << alu_b[4:0];
            4'd6: alu_result = alu_a >> alu_b[4:0];
            4'd7: alu_result = $signed(alu_a) >>> alu_b[4:0];
            4'd8: alu_result = ($signed(alu_a) < $signed(alu_b)) ? 32'd1 : 32'd0;
            4'd9: alu_result = (alu_a < alu_b) ? 32'd1 : 32'd0;
            default: alu_result = 32'b0;
        endcase
    end

    // ── Branch Unit ───────────────────────────────────────────────
    reg branch_taken;
    always @(*) begin
        case (funct3)
            3'b000: branch_taken = (rs1_data == rs2_data);
            3'b001: branch_taken = (rs1_data != rs2_data);
            3'b100: branch_taken = ($signed(rs1_data) <  $signed(rs2_data));
            3'b101: branch_taken = ($signed(rs1_data) >= $signed(rs2_data));
            3'b110: branch_taken = (rs1_data <  rs2_data);
            3'b111: branch_taken = (rs1_data >= rs2_data);
            default: branch_taken = 1'b0;
        endcase
    end

    // ── Load Data ─────────────────────────────────────────────────
    reg [31:0] load_data;
    always @(*) begin
        case (funct3)
            3'b000: load_data = {{24{dmem_rdata[7]}},  dmem_rdata[7:0]};   // LB
            3'b001: load_data = {{16{dmem_rdata[15]}}, dmem_rdata[15:0]};  // LH
            3'b010: load_data = dmem_rdata;                                  // LW
            3'b100: load_data = {24'b0, dmem_rdata[7:0]};                   // LBU
            3'b101: load_data = {16'b0, dmem_rdata[15:0]};                  // LHU
            default: load_data = 32'b0;
        endcase
    end

    // ── Store Data & Byte Enable ──────────────────────────────────
    reg [31:0] store_data;
    reg [3:0]  store_be;
    always @(*) begin
        case (funct3)
            3'b000: begin  // SB
                store_data = {4{rs2_data[7:0]}};
                store_be   = 4'b0001 << alu_result[1:0];
            end
            3'b001: begin  // SH
                store_data = {2{rs2_data[15:0]}};
                store_be   = 4'b0011 << alu_result[1:0];
            end
            3'b010: begin  // SW
                store_data = rs2_data;
                store_be   = 4'b1111;
            end
            default: begin
                store_data = 32'b0;
                store_be   = 4'b0000;
            end
        endcase
    end

    // ── Memory outputs ────────────────────────────────────────────
    assign mem_we     = mem_we_r;
    assign mem_be     = store_be;
    assign dmem_addr  = alu_result;
    assign dmem_wdata = store_data;

    // ── Writeback data ────────────────────────────────────────────
    wire [31:0] wb_data = (opcode == OP_LUI)                  ? imm_sel      :
                          (opcode == OP_JAL || opcode == OP_JALR) ? pc + 32'd4 :
                          mem_re                               ? load_data    :
                                                                 alu_result;

    // ── PC next ───────────────────────────────────────────────────
    wire [31:0] pc_branch = pc + imm_b;
    wire [31:0] pc_jal    = pc + imm_j;
    wire [31:0] pc_jalr   = (rs1_data + imm_i) & 32'hFFFF_FFFE;
    wire [31:0] pc_next   = (opcode == OP_JAL)                        ? pc_jal    :
                            (opcode == OP_JALR)                        ? pc_jalr   :
                            (opcode == OP_BRANCH && branch_taken)      ? pc_branch :
                                                                          pc + 32'd4;

    // ── Clocked updates ───────────────────────────────────────────
    integer i;
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            pc <= 32'b0;
            for (i = 0; i < 32; i = i + 1)
                regs[i] <= 32'b0;
        end else begin
            pc <= pc_next;
            if (reg_we && rd != 5'b0)
                regs[rd] <= wb_data;
        end
    end

endmodule