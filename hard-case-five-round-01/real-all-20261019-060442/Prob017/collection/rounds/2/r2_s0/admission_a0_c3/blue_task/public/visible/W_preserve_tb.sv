module tb;
reg clk=0,rst=0;wire clk_out;reg held;integer i;
TopModule dut(clk,rst,clk_out);
initial begin
 #2;clk=1;#2;clk=0;#2;rst=1;
 for(i=0;i<100;i=i+1) begin
  #3;clk=1;#2;held=clk_out;#1;clk=0;#1;
  if(clk_out!==held) begin $display("CHECK_FAIL output changed without rising edge");$finish;end
  if(held===1'b1) begin
   rst=0;#1;
   if(clk_out!==0) begin $display("CHECK_FAIL asynchronous reset");$finish;end
   rst=1;#1;
   if(clk_out!==0) begin $display("CHECK_FAIL reset release");$finish;end
   $display("TESTBENCH PASS divider preserve");$finish;
  end
 end
 $display("CHECK_FAIL output never became high");$finish;
end
endmodule
