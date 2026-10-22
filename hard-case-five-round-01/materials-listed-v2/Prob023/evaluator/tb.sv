module tb;
reg clk=0,rst_n=0;wire [3:0] gray_out;integer cycle;reg[3:0] binary_expected,expected;
TopModule dut(clk,rst_n,gray_out);
initial begin
 #2;clk=1;#2;clk=0;#2;rst_n=1;
 for(cycle=0;cycle<512;cycle=cycle+1) begin
  #5;clk=1;#3;
  binary_expected=(cycle+1)/2;
  expected=(binary_expected>>1)^binary_expected;
  if(gray_out!==expected) begin $display("CHECK_FAIL gray cycle=%0d got=%b expected=%b",cycle,gray_out,expected);$finish;end
  #1;clk=0;
 end
 $display("TESTBENCH PASS gray cycles=256");$finish;
end
endmodule
