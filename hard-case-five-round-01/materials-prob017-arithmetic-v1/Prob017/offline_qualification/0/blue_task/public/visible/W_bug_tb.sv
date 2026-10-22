module divider_check #(parameter MN=87,C=24,E=8,O=9,ID=0)(input clk,rst);
wire result; integer count=0,cycle_count=0,mode=0; reg expected;
TopModule #(.M_N(MN),.c89(C),.div_e(E),.div_o(O)) dut(clk,rst,result);
always @(posedge clk) begin
 if(!rst) begin count=0;cycle_count=0;mode=0;expected=0;end
 else begin
  expected=(count<=((mode?O:E)/4+1));
  count=(count==((mode?O:E)-1))?0:(count+1)%16;
  if(cycle_count==MN-1 || cycle_count==C-1) mode=1-mode;
  cycle_count=(cycle_count==MN-1)?0:cycle_count+1;
 end
 #1;
 if(result!==expected) begin $display("CHECK_FAIL divider config=%0d got=%b expected=%b count=%0d cycle=%0d mode=%0d",ID,result,expected,count,cycle_count,mode);$finish;end
end
endmodule
module tb;
reg clk=0,rst=0;integer i;
divider_check #(87,24,8,9,0) a(clk,rst);
divider_check #(17,6,4,5,1) b(clk,rst);
divider_check #(47,15,12,13,2) c(clk,rst);
divider_check #(31,9,6,7,3) d(clk,rst);
initial begin
 for(i=0;i<1400;i=i+1) begin
  rst=!(i<3 || (i>=93 && i<96) || (i>=721 && i<723));
  #3;clk=1;#2;clk=0;#2;
 end
 $display("TESTBENCH PASS divider public waveform");$finish;
end
endmodule
