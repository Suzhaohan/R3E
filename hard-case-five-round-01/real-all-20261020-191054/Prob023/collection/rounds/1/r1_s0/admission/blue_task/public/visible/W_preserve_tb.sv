module tb;
reg clk=0,rst_n=0;wire [3:0] gray_out;integer i;reg[3:0] held;
TopModule dut(clk,rst_n,gray_out);
initial begin
 #2;clk=1;#2;clk=0;#2;rst_n=1;
 for(i=0;i<8;i=i+1) begin #3;clk=1;#2;held=gray_out;#1;clk=0;#2;
  if(gray_out!==held) begin $display("CHECK_FAIL output must hold without rising edge");$finish;end
 end
 rst_n=0;#1;
 if(gray_out!==0) begin $display("CHECK_FAIL asynchronous reset");$finish;end
 rst_n=1;#1;
 if(gray_out!==0) begin $display("CHECK_FAIL reset release");$finish;end
 $display("TESTBENCH PASS gray preserve");$finish;
end
endmodule
