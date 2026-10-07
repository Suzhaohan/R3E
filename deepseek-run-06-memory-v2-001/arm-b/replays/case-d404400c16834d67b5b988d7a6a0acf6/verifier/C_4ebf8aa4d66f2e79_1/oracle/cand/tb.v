module tb;
reg [3:0] a;
wire [6:0] actual, expected;
decl7s_test dut(.a(a),.led7s(actual[6:0]));
r3e_reference oracle(.a(a),.led7s(expected[6:0]));
integer i, fd, bad, first;
initial begin
 fd=$fopen("output.csv","w"); $fdisplay(fd,"time,actual"); bad=0; first=-1;
 for(i=0;i<16;i=i+1) begin
  {a}=i; #1; $fdisplay(fd,"%0d,%b",i,actual);
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
module r3e_reference(a,led7s);
      input [3:0] a;
      output [6:0] led7s;
      reg [6:0] led7s;
always @(a)



begin
case(a)
  4'b0000: led7s=7'b0111111;
  4'b0001: led7s=7'b0000110;
  4'b0010: led7s=7'b1011011;
  4'b0011: led7s=7'b1001111;
  4'b0100: led7s=7'b1100110;
  4'b0101: led7s=7'b1101101;
  4'b0110: led7s=7'b1111101;
  4'b0111: led7s=7'b0000111;
  4'b1000: led7s=7'b1111111;
  4'b1001: led7s=7'b1101111;
  4'b1010: led7s=7'b1110111;
  4'b1011: led7s=7'b1111100;
  4'b1100: led7s=7'b0111001;
  4'b1101: led7s=7'b1011110;
  4'b1110: led7s=7'b1111001;
  4'b1111: led7s=7'b1110001;
endcase
end 


endmodule    
       