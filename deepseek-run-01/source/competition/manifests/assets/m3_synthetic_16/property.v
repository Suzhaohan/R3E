module formal_top; (* anyconst *) reg [3:0] a,b; wire y; m dut(.a(a),.b(b),.y(y)); always @* assert(y == ((a < 3) && (b > 10))); endmodule
