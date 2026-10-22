module tb;
reg clk=0,rst_n=0,a=0;wire match;reg [8:0] history=0;
integer word,j,checks=0;reg expected;
TopModule dut(clk,rst_n,a,match);
task step(input bit_in);
begin
 clk=0;a=bit_in;#2;
 expected=(history[8:6]==3'b011 && history[2:0]==3'b110);
 clk=1;#2;
 if(match!==expected) begin $display("CHECK_FAIL wildcard cycle=%0d history=%b got=%b expected=%b",checks,history,match,expected);$finish;end
 history={history[7:0],bit_in};checks=checks+1;clk=0;#2;
end
endtask
initial begin
 #2;clk=1;#2;clk=0;#2;rst_n=1;
 for(word=0;word<512;word=word+1) begin
  for(j=8;j>=0;j=j-1) step((9'b011000110>>j)&1);
  for(j=8;j>=0;j=j-1) step((word>>j)&1);
 end
 $display("TESTBENCH PASS wildcard checks=%0d",checks);$finish;
end
endmodule
