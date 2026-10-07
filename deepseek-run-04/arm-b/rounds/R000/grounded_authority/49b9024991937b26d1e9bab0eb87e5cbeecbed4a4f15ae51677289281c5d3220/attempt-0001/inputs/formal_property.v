module formal_top;
(* anyconst *) reg a;
(* anyconst *) reg b;
(* anyconst *) reg s;
wire [0:0] actual, expected;
mux21 dut(.a(a),.b(b),.s(s),.y(actual[0]));
r3e_reference oracle(.a(a),.b(b),.s(s),.y(expected[0]));
always @* assert(actual == expected);
endmodule
module r3e_reference(a,b,s,y);
	input a,b,s;
	output y;
	reg y;
	always @(a,b,s)
    
        

	if(s==0) y=a;
	else y=b;
        

	
endmodule