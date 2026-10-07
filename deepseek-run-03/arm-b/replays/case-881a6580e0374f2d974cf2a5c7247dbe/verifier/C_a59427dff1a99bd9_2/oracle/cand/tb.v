module tb;
reg [2:0] a;
reg ena;
wire [7:0] actual, expected;
decoder3e_test dut(.a(a),.ena(ena),.y(actual[7:0]));
r3e_reference oracle(.a(a),.ena(ena),.y(expected[7:0]));
integer i, fd, bad, first;
initial begin
 fd=$fopen("output.csv","w"); $fdisplay(fd,"time,actual"); bad=0; first=-1;
 for(i=0;i<16;i=i+1) begin
  {a,ena}=i; #1; $fdisplay(fd,"%0d,%b",i,actual);
  if(actual !== expected) begin bad=bad+1; if(first<0) first=i; end
 end
 $fclose(fd);
 if(bad==0) begin
  $display("R3E_ORACLE pass=1 signature=none first=none topology=none");
  $display("R3E_WAVEFORM signal=none first_cycle=none cycle_offset=none relation=none assignment=none cone_depth=none pattern=none");
 end else begin
  $display("R3E_ORACLE pass=0 signature=output_mismatch first=vector%0d topology=actual",first);
  $display("R3E_WAVEFORM signal=actual first_cycle=%0d cycle_offset=0 relation=same_cycle assignment=procedural cone_depth=1 pattern=output_mismatch",first);
 end
 $finish;
end
endmodule


module r3e_reference(a,ena,y);
  input [2:0] a;
  input ena;
  output [7:0] y; 
  reg[7:0] Y;
  


always @(ena or a)
begin
if(ena==0)
Y=8'b0000_0000;
else
case (a)
3'b000: Y=8'b0000_0001;
3'b001: Y=8'b0000_0010;
3'b010: Y=8'b0000_0100;
3'b011: Y=8'b0000_1000;
3'b100: Y=8'b0001_0000;
3'b101: Y=8'b0010_0000;
3'b110: Y=8'b0100_0000;
3'b111: Y=8'b1000_0000;
endcase
end
assign y=Y;





endmodule
