module tb;
reg [2:0] ABC;
wire [1:0] actual, expected;
JG3 dut(.ABC(ABC),.X(actual[0]),.Y(actual[1]));
r3e_reference oracle(.ABC(ABC),.X(expected[0]),.Y(expected[1]));
integer i, fd, bad, first;
initial begin
 fd=$fopen("output.csv","w"); $fdisplay(fd,"time,actual"); bad=0; first=-1;
 for(i=0;i<8;i=i+1) begin
  {ABC}=i; #1; $fdisplay(fd,"%0d,%b",i,actual);
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
module r3e_reference(ABC,X,Y);
	
	input [2:0] ABC;
	
	output X, Y;
	reg X, Y;
	
	always@(ABC)
    
        

case(ABC)
3'b000 : begin X = 0; Y = 1; end
3'b001 : begin X = 0; Y = 0; end
3'b010 : begin X = 0; Y = 0; end
3'b011 : begin X = 0; Y = 0; end
3'b100 : begin X = 0; Y = 0; end
3'b101 : begin X = 1; Y = 0; end
3'b110 : begin X = 1; Y = 0; end
3'b111 : begin X = 1; Y = 0; end
default :;
endcase
        

	
endmodule