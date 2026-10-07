module m(input wire [3:0] a, input wire [3:0] b, output wire y);
 assign y = (a < 11) && (b > 5);
endmodule
