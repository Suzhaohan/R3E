//`include "fsm_full.v"

module tb;
integer sample_index=0, errors=0; reg [3:0] expected;

reg clock , reset ;
reg instrument_clock;
reg req_0 , req_1 ,  req_2 , req_3; 
wire gnt_0 , gnt_1 , gnt_2 , gnt_3 ;

integer f;

initial begin
  $dumpfile("output_fsm_full_tb_t1.vcd");
  $dumpvars();
  f = $fopen("output_fsm_full_tb_t1.txt");
  $display("time\t    req_0 req_1 req_2 req_3 gnt_0 gnt_1 gnt_2 gnt_3");
  $fwrite(f, "time,gnt_0,gnt_1,gnt_2,gnt_3\n");
  $monitor("%g\t    %b  %b  %b  %b  %b  %b  %b  %b", 
    $time, req_0, req_1, req_2, req_3, gnt_0, gnt_1, gnt_2, gnt_3);
  forever begin
    @(posedge clock);
    case(sample_index)
0: expected=4'bxxxx;
1: expected=4'bxxxx;
2: expected=4'b0000;
3: expected=4'b0000;
4: expected=4'b0000;
5: expected=4'b0000;
6: expected=4'b0000;
7: expected=4'b0000;
8: expected=4'b0000;
9: expected=4'b0000;
10: expected=4'b1000;
11: expected=4'b1000;
12: expected=4'b1000;
13: expected=4'b1000;
14: expected=4'b1000;
15: expected=4'b0000;
16: expected=4'b0000;
17: expected=4'b0100;
18: expected=4'b0100;
19: expected=4'b0100;
20: expected=4'b0100;
21: expected=4'b0100;
22: expected=4'b0000;
23: expected=4'b0000;
24: expected=4'b0000;
25: expected=4'b0010;
26: expected=4'b0010;
27: expected=4'b0010;
28: expected=4'b0010;
29: expected=4'b0010;
30: expected=4'b0000;
31: expected=4'b0000;
32: expected=4'b0001;
33: expected=4'b0001;
34: expected=4'b0001;
35: expected=4'b0001;
36: expected=4'b0001;
37: expected=4'b0000;
default: begin $display("CHECK_FAIL excess oracle samples"); errors=errors+1; end
endcase
if (!(expected === (expected ^ {gnt_0,gnt_1,gnt_2,gnt_3} ^ expected))) begin
 $display("CHECK_FAIL oracle sample=%0d got=%b expected=%b",sample_index,{gnt_0,gnt_1,gnt_2,gnt_3},expected);
 errors=errors+1;
end
sample_index=sample_index+1;
$fwrite(f, "%g,%b,%b,%b,%b\n", 
     $time, gnt_0, gnt_1, gnt_2, gnt_3);
  end
end

initial begin
  #4
  clock = 0;
  instrument_clock = 0;
  reset = 0;
  req_0 = 0;
  req_1 = 0;
  req_2 = 0;
  req_3 = 0;
  #10 reset = 1;
  #10 reset = 0;
  #10 req_0 = 1;
  #20 req_0 = 0;
  #10 req_1 = 1;
  #20 req_1 = 0;
  #10 req_2 = 1;
  #20 req_2 = 0;
  #10 req_3 = 1;
  #20 req_3 = 0;
  #10
  $fclose(f);
  $finish;
end

always
 #2 clock = ~clock;

always
  #8 instrument_clock = ~instrument_clock;

fsm_full U_fsm_full(
clock , // Clock
reset , // Active high reset
req_0 , // Active high request from agent 0
req_1 , // Active high request from agent 1
req_2 , // Active high request from agent 2
req_3 , // Active high request from agent 3
gnt_0 , // Active high grant to agent 0
gnt_1 , // Active high grant to agent 1
gnt_2 , // Active high grant to agent 2
gnt_3   // Active high grant to agent 3
);




final begin
 if(errors==0 && sample_index==38) $display("TESTBENCH PASS original oracle");
 else $display("CHECK_FAIL oracle errors=%0d samples=%0d",errors,sample_index);
end

endmodule
