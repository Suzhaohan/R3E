module tb;
reg clk=0,rst=0,d1=1,d2=0,sel=0;wire out1,out2,out3;integer j;
TopModule dut(clk,rst,d1,d2,sel,out1,out2,out3);
initial begin
#2;clk=1;#2;clk=0;rst=1;
for(j=0;j<3;j=j+1) begin #2;clk=1;#2;clk=0;end
d1=0;rst=0;#2;
if({out1,out2,out3}!==0) begin $display("CHECK_FAIL reset outputs");$finish;end
rst=1;#2;
if({out1,out2,out3}!==0) begin $display("CHECK_FAIL asynchronous state reset");$finish;end
$display("TESTBENCH PASS preserve");$finish;
end
endmodule
