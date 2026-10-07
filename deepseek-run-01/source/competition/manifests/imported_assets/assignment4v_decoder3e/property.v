module formal_top;
(* anyconst *) reg [2:0] a;
(* anyconst *) reg ena;
wire [7:0] actual, expected;
decoder3e_test dut(.a(a),.ena(ena),.y(actual[7:0]));
r3e_reference oracle(.a(a),.ena(ena),.y(expected[7:0]));
always @* assert(actual == expected);
endmodule


module r3e_reference(a,ena,y);
  input [2:0] a;
  input ena;
  output [7:0] y; 

  


reg [7:0]y;
always@(a or ena)begin
  if(~ena) y=8'd0;
  else 
    case(a)
      3'b000: y<=8'd1;
      3'b001: y<=8'd2;
      3'b010: y<=8'd4;
      3'b011: y<=8'd8;
      3'b100: y<=8'd16;
      3'b101: y<=8'd32;
      3'b110: y<=8'd64;
      3'b111: y<=8'd128;
  endcase
end





endmodule
