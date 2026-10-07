module formal_top;
(* anyconst *) reg [2:0] ABC;
wire [1:0] actual, expected;
JG3 dut(.ABC(ABC),.X(actual[0]),.Y(actual[1]));
r3e_reference oracle(.ABC(ABC),.X(expected[0]),.Y(expected[1]));
always @* assert(actual == expected);
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