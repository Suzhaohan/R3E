module formal_top;
(* anyconst *) reg a;
(* anyconst *) reg b;
(* anyconst *) reg ci;
wire [1:0] actual, expected;
fa_behavioral dut(.a(a),.b(b),.ci(ci),.s(actual[0]),.co(actual[1]));
r3e_reference oracle(.a(a),.b(b),.ci(ci),.s(expected[0]),.co(expected[1]));
always @* assert(actual == expected);
endmodule
module r3e_reference(a,b,ci,s,co);
       input a,b;
       input ci;
       output  s;
       output co;



       assign s=(a^b^ci);
       assign co=((a&b)|(a&ci)|(b&ci));



endmodule
