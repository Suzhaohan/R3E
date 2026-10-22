module tb;
reg [3:0] a=0,b=2,c=4,d=8;reg [1:0] sel=0;wire [3:0] out;integer i;
mux_4to1_case dut(a,b,c,d,sel,out);
initial begin
#1;a=15;#2;
for(i=0;i<16;i=i+1) begin a=i;#2;
if(out!==a) begin $display("CHECK_FAIL preserve selected a");$finish;end end
$display("TESTBENCH PASS preserve");$finish;end
endmodule
