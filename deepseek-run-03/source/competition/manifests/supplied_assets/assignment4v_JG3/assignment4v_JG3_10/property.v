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
			3'd0: begin X<=0;Y<=1; end
			3'd5: begin X<=1;Y=0; end
			3'd6: begin X<=1;Y=0; end
			3'd7: begin X<=1;Y=0; end
			default: begin X<=0;Y=0; end
		endcase	
		
        

	
endmodule