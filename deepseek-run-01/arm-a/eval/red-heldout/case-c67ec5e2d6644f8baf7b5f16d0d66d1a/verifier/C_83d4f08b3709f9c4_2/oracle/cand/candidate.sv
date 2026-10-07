module m(input wire [3:0] a, input wire [3:0] b, output wire y);
 assign y = (a <= 4'd8) || (b > 4'd9);
endmodule
