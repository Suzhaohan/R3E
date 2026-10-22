`timescale 1ns/1ps
module tb_witness;
  reg clk = 0, rst = 1, d1 = 0, d2 = 0, sel = 0;
  wire out1, out2, out3;
  integer errors = 0;
  always #5 clk = ~clk;
  TopModule dut(.clk(clk), .rst(rst), .d1(d1), .d2(d2), .sel(sel),
                .out1(out1), .out2(out2), .out3(out3));

  task restart(input selection);
    begin
      @(negedge clk); rst = 0; d1 = 0; d2 = 0; sel = selection;
      @(posedge clk); #1;
    end
  endtask

  task coin(input half_yuan, input one_yuan, input [2:0] expected);
    begin
      @(negedge clk); rst = 1; d1 = half_yuan; d2 = one_yuan;
      @(posedge clk); #1;
      if ({out1, out2, out3} !== expected) begin
        errors = errors + 1;
        $display("MISMATCH sel=%b d1=%b d2=%b got=%b%b%b expected=%b",
                 sel, d1, d2, out1, out2, out3, expected);
      end
    end
  endtask

  initial begin
    // S0_5 + d2: 0.5 + 1 yuan must dispense the 1.5-yuan beverage.
    restart(0);
    coin(1, 0, 3'b000);
    coin(0, 1, 3'b100);
    // Reach S1_5 via S1 + d1, independently of the first mutated transition.
    // S1_5 + d2: 1.5 + 1 yuan must dispense the 2.5-yuan beverage.
    restart(1);
    coin(0, 1, 3'b000);
    coin(1, 0, 3'b000);
    coin(0, 1, 3'b010);
    if (errors) $fatal(1, "WITNESS_FAIL errors=%0d", errors);
    $display("WITNESS_PASS");
    $finish;
  end
  initial begin #2000; $fatal(1, "TIMEOUT"); end
endmodule
