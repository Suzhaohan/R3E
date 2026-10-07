module m(input wire [3:0] a, input wire [3:0] b, output wire y);
 assign y = (a < 4'd3) || (b > 4'd4);
endmodule
