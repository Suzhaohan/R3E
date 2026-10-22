`timescale 1ns/1ps
module tb_witness;
  reg clk = 0, rst_n = 1, data = 0;
  wire match, not_match;
  integer errors = 0;
  always #5 clk = ~clk;
  TopModule dut(.clk(clk), .rst_n(rst_n), .data(data),
                .match(match), .not_match(not_match));

  task run_stream(input [11:0] stream, input first_group_matches);
    integer i;
    reg expected_match, expected_not_match;
    begin
      @(negedge clk); rst_n = 0; data = 0;
      @(posedge clk); #1;
      for (i = 0; i < 12; i = i + 1) begin
        @(negedge clk); rst_n = 1; data = stream[11-i];
        @(posedge clk); #1;
        expected_match = (i == 5 && first_group_matches) || i == 11;
        expected_not_match = i == 5 && !first_group_matches;
        if ({match, not_match} !== {expected_match, expected_not_match}) begin
          errors = errors + 1;
          $display("MISMATCH stream=%b bit=%0d got=%b%b expected=%b%b",
                   stream, i+1, match, not_match, expected_match, expected_not_match);
        end
      end
    end
  endtask

  initial begin
    // Exercise both s6 and sf6 boundaries using legal, back-to-back groups.
    run_stream(12'b011100011100, 1'b1);
    run_stream(12'b111111011100, 1'b0);
    if (errors) $fatal(1, "WITNESS_FAIL errors=%0d", errors);
    $display("WITNESS_PASS");
    $finish;
  end
  initial begin #2000; $fatal(1, "TIMEOUT"); end
endmodule
