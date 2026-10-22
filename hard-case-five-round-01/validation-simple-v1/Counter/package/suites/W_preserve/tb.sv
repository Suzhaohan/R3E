module tb;
reg clk=0,reset=1,enable=0;wire [3:0] counter_out;wire overflow_out;integer i;
first_counter dut(clk,reset,enable,counter_out,overflow_out);
task tick;begin #3;clk=1;#3;clk=0;#3;end endtask
initial begin tick;reset=0;enable=1;
for(i=1;i<8;i=i+1) begin tick;if(counter_out!==i || overflow_out!==0) begin
$display("CHECK_FAIL preserve low count");$finish;end end
reset=1;tick;
if(counter_out!==0 || overflow_out!==0) begin $display("CHECK_FAIL reset with enable");$finish;end
$display("TESTBENCH PASS preserve");$finish;end
endmodule
