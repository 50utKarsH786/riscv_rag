`timescale 1ns/1ps

module testbench;
    reg clk;
    reg rst;
    
    // Core signals
    wire [31:0] imem_rdata;
    wire [31:0] imem_addr;
    wire        mem_we;
    wire [3:0]  mem_be;
    wire        mem_re;
    wire [31:0] dmem_addr;
    wire [31:0] dmem_wdata;
    reg  [31:0] dmem_rdata;

    // Instantiate the RISC-V Core
    riscv_core uut (
        .clk(clk),
        .rst(rst),
        .imem_rdata(imem_rdata),
        .imem_addr(imem_addr),
        .mem_we(mem_we),
        .mem_be(mem_be),
        .mem_re(mem_re),
        .dmem_addr(dmem_addr),
        .dmem_wdata(dmem_wdata),
        .dmem_rdata(dmem_rdata)
    );

    // 16KB Memory (Word addressed for simplicity of simple tests)
    reg [31:0] memory [0:4095];

    // Clock generation
    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    // Instruction Memory Read
    assign imem_rdata = (imem_addr[31:2] < 4096) ? memory[imem_addr[31:2]] : 32'h00000013; // NOP default

    // Data Memory Read/Write
    always @(negedge clk) begin
        if (mem_re) begin
            dmem_rdata <= (dmem_addr[31:2] < 4096) ? memory[dmem_addr[31:2]] : 32'b0;
        end
        if (mem_we) begin
            if (dmem_addr[31:2] < 4096) begin
                if (mem_be[0]) memory[dmem_addr[31:2]][7:0]   <= dmem_wdata[7:0];
                if (mem_be[1]) memory[dmem_addr[31:2]][15:8]  <= dmem_wdata[15:8];
                if (mem_be[2]) memory[dmem_addr[31:2]][23:16] <= dmem_wdata[23:16];
                if (mem_be[3]) memory[dmem_addr[31:2]][31:24] <= dmem_wdata[31:24];
            end
        end
    end

    integer pass_count = 0;
    integer fail_count = 0;

    task check;
        input [80*8:1] name;
        input [31:0] got;
        input [31:0] expected;
        begin
            if (got === expected) begin
                $display("  [PASS] %0s = 0x%08x", name, got);
                pass_count = pass_count + 1;
            end else begin
                $display("  [FAIL] %0s_ expected=0x%08x got=0x%08x", name, expected, got);
                fail_count = fail_count + 1;
            end
        end
    endtask

    integer i;

    // Main Test Sequence
    initial begin
        $display("========================================");
        $display("   RISC-V RAG Core EDA Testbench      ");
        $display("========================================");

        // EDA Playground Waveform dumping
        $dumpfile("dump.vcd");
        $dumpvars(0, testbench);

        // Clear memory
        for (i = 0; i < 4096; i = i + 1) memory[i] = 0;

        // --- TEST 1: ALU Operations ---
        $display("\n=== TEST 1: ALU Operations ===");
        memory[0]  = 32'h00500093; // addi x1, x0, 5
        memory[1]  = 32'h00300113; // addi x2, x0, 3
        memory[2]  = 32'h002081B3; // add  x3, x1, x2  (8)
        memory[3]  = 32'h40208233; // sub  x4, x1, x2  (2)
        memory[4]  = 32'h0020F2B3; // and  x5, x1, x2  (1)
        memory[5]  = 32'h0020E333; // or   x6, x1, x2  (7)
        memory[6]  = 32'h0020C3B3; // xor  x7, x1, x2  (6)
        memory[7]  = 32'h10000413; // addi x8, x0, 256
        memory[8]  = 32'h00342023; // sw x3, 0(x8)   (Addr 256 -> Word 64)
        memory[9]  = 32'h00442223; // sw x4, 4(x8)   (Addr 260 -> Word 65)
        memory[10] = 32'h00542423; // sw x5, 8(x8)   (Addr 264 -> Word 66)
        memory[11] = 32'h00642623; // sw x6, 12(x8)  (Addr 268 -> Word 67)
        memory[12] = 32'h00742823; // sw x7, 16(x8)  (Addr 272 -> Word 68)
        memory[13] = 32'h00000013; // nop
        
        rst = 1;
        #25;
        rst = 0;
        #200; // Wait 20 clock cycles

        check("ADD  x3", memory[64], 32'd8);
        check("SUB  x4", memory[65], 32'd2);
        check("AND  x5", memory[66], 32'd1);
        check("OR   x6", memory[67], 32'd7);
        check("XOR  x7", memory[68], 32'd6);


        // --- TEST 2: Branch Instructions ---
        $display("\n=== TEST 2: Branch Instructions ===");
        for (i = 0; i < 4096; i = i + 1) memory[i] = 0;
        memory[0] = 32'h00500093; // addi x1, x0, 5
        memory[1] = 32'h00500113; // addi x2, x0, 5
        memory[2] = 32'h00208463; // beq x1, x2, +8 (skip mem[3])
        memory[3] = 32'h06300193; // addi x3, x0, 99  (should skip)
        memory[4] = 32'h02A00193; // addi x3, x0, 42
        memory[5] = 32'h10000413; // addi x8, x0, 256
        memory[6] = 32'h00342023; // sw x3, 0(x8)
        memory[7] = 32'h00000013; // nop

        rst = 1;
        #25;
        rst = 0;
        #200;

        check("BEQ taken: x3", memory[64], 32'd42);

        // --- TEST 3: LUI and AUIPC ---
        $display("\n=== TEST 3: LUI and AUIPC ===");
        for (i = 0; i < 4096; i = i + 1) memory[i] = 0;
        memory[0] = 32'h000010B7; // lui x1, 1  -> x1 = 0x1000
        memory[1] = 32'h10000413; // addi x8, x0, 256
        memory[2] = 32'h00142023; // sw x1, 0(x8)
        memory[3] = 32'h00000013; // nop
        
        rst = 1;
        #25;
        rst = 0;
        #150;

        check("LUI x1", memory[64], 32'h1000);

        // Final Report
        $display("\n========================================");
        $display("RESULTS: %0d passed, %0d failed out of %0d tests", pass_count, fail_count, (pass_count + fail_count));
        $display("========================================\n");

        $finish;
    end

endmodule
