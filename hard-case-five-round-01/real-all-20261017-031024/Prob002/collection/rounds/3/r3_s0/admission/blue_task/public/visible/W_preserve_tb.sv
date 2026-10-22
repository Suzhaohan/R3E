module tb;
reg clk=0,rst_n=0,a=0;wire match;integer j;
TopModule dut(clk,rst_n,a,match);
initial begin
 #2;clk=1;#2;clk=0;#2;rst_n=1;
 for(j=8;j>=0;j=j-1) begin a=(9'b011000110>>j)&1;#2;clk=1;#2;clk=0;end
 a=0;#2;clk=1;#2;clk=0;
 rst_n=0;#2;
 if(match!==0) begin $display("CHECK_FAIL async reset");$finish;end
 rst_n=1;#2;
 if(match!==0) begin $display("CHECK_FAIL reset release");$finish;end
 $display("TESTBENCH PASS reset");$finish;
end
endmodule
