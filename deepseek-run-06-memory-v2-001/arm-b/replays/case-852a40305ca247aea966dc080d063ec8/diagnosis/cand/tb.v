module tb;
reg a;
reg b;
reg s;
wire [0:0] actual, expected;
mux21 dut(.a(a),.b(b),.s(s),.y(actual[0]));
r3e_reference oracle(.a(a),.b(b),.s(s),.y(expected[0]));
integer i, fd, bad, first;
initial begin
 fd=$fopen("output.csv","w"); $fdisplay(fd,"time,actual"); bad=0; first=-1;
 for(i=0;i<8;i=i+1) begin
  {a,b,s}=i; #1; $fdisplay(fd,"%0d,%b",i,actual);
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
module r3e_reference(a,b,s,y);
	input a,b,s;
	output y;
	reg y;
	always @(a,b,s)
    
        

if(s==1'B0)begin y=a;end
else begin y=b;end
        

	
endmodule