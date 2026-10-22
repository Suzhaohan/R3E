module tb;
reg clk=0,rst=0,d1=0,d2=1,sel=0;wire out1,out2,out3;
integer amount=0,word,j,s,checks=0;reg [2:0] expected;
TopModule dut(clk,rst,d1,d2,sel,out1,out2,out3);
task check_outputs;
begin
 case(amount)
 0,1,2:expected=0;
 3:expected=sel?3'b000:3'b100;
 4:expected=sel?3'b000:3'b101;
 5:expected=sel?3'b010:3'b101;
 6:expected=sel?3'b011:3'b101;
 default:expected=0;
 endcase
 if({out1,out2,out3}!==expected) begin
 $display("CHECK_FAIL vending check=%0d amount=%0d sel=%b got=%b%b%b expected=%b",checks,amount,sel,out1,out2,out3,expected);$finish;end
 checks=checks+1;
end
endtask
task reset;
begin clk=0;rst=0;d1=0;d2=1;#2;clk=1;#2;clk=0;#2;rst=1;amount=0;#2;end
endtask
task coin(input one_yuan);
begin
 clk=0;d1=!one_yuan;d2=one_yuan;#2;
 if((amount==3 || amount==4) && !sel) amount=0;
 else if(amount>=5) amount=0;
 else amount=amount+(one_yuan?2:1);
 clk=1;#2;check_outputs;clk=0;#2;
end
endtask
initial begin
for(s=0;s<2;s=s+1) begin
sel=s;
for(word=0;word<64;word=word+1) begin reset;for(j=5;j>=0;j=j-1) coin((word>>j)&1);end
end
$display("TESTBENCH PASS vending");$finish;
end
endmodule
