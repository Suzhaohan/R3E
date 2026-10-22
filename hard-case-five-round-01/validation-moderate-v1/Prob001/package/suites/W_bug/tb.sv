module tb;
reg clk=0, rst_n=0, a=0; wire match;
reg [7:0] history=0; integer word,j,check_count=0;
TopModule dut(clk,rst_n,a,match);
task reset;
begin clk=0;rst_n=0;#2;clk=1;#2;clk=0;#2;rst_n=1;history=0;end
endtask
task bit_step(input b);
reg expected;
begin
 clk=0;a=b;#2;expected=(history==8'b01110001);clk=1;#2;
 if(match!==expected) begin $display("CHECK_FAIL sequence sample=%0d",check_count);$finish;end
 history={history[6:0],b};check_count=check_count+1;clk=0;#2;
end
endtask
initial begin
reset;
for(word=0;word<256;word=word+1) begin
 for(j=7;j>=0;j=j-1) bit_step((8'b01110001>>j)&1);
 for(j=7;j>=0;j=j-1) bit_step((word>>j)&1);
end
$display("TESTBENCH PASS sequence");$finish;
end
endmodule
