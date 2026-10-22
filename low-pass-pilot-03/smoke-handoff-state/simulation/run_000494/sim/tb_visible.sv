`timescale 1ns/1ps
module prob003_trace;
  reg clk = 0, rst_n = 0, data = 0;
  wire match, not_match;
  integer trace_file, stimulus_file, group_index, bit_index;
  TopModule dut(clk, rst_n, data, match, not_match);

  task sample;
    begin
      $fdisplay(trace_file, "%0d,%b,%b", $time, match, not_match);
      $fdisplay(stimulus_file, "%0d,%b,%b,%b", $time, clk, rst_n, data);
    end
  endtask

  task reset;
    begin
      clk = 0; rst_n = 0; #2; sample;
      clk = 1; #2; clk = 0; #2; rst_n = 1; #1; sample;
    end
  endtask

  task group(input [5:0] bits);
    integer position;
    begin
      for (position = 5; position >= 0; position = position - 1) begin
        clk = 0; data = bits[position]; #2; clk = 1; #2; sample;
        clk = 0; #2;
      end
    end
  endtask

  task preserve_tick(input value);
    begin
      clk = 0; data = value; #2; clk = 1; #2; sample;
      data = ~value; #2; sample;
      clk = 0; #2;
    end
  endtask

  initial begin
    trace_file = $fopen("trace_visible.txt", "w");
    stimulus_file = $fopen("stimulus_visible.txt", "w");
    $fdisplay(trace_file, "time,match,not_match");
    $fdisplay(stimulus_file, "time,clk,rst_n,data");
    reset;
    for (group_index = 0; group_index < 64; group_index = group_index + 1) begin
      group(6'b011100);
      group(group_index);
      group(6'b100011);
      group(6'b011100);
    end
    reset;
    for (group_index = 0; group_index < 64; group_index = group_index + 1)
      for (bit_index = 5; bit_index >= 0; bit_index = bit_index - 1)
        preserve_tick((group_index >> bit_index) & 1);
    reset;
    preserve_tick(0); preserve_tick(1); preserve_tick(1);
    preserve_tick(1); preserve_tick(0); preserve_tick(0);
    rst_n = 0; #2; sample;
    rst_n = 1; #2; sample;
    $fclose(trace_file);
    $fclose(stimulus_file);
    $finish;
  end
endmodule
