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
  output reg [7:0] y; 

  


always @(*)begin
  if(!ena) y = 0;
  else begin
    case(a)
        3'b000: y = 8'b0000_0001;
        3'b001: y = 8'b0000_0010;
        3'b010: y = 8'b0000_0100;
        3'b011: y = 8'b0000_1000;
        3'b100: y = 8'b0001_0000;
        3'b101: y = 8'b0010_0000;
        3'b110: y = 8'b0100_0000;
        3'b111: y = 8'b1000_0000;
    
    endcase
  end
end





endmodule
