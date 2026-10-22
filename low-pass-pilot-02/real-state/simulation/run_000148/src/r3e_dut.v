module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);

   reg [3:0] bin;
   reg slow;

   function [3:0] gray2bin;
      input [3:0] g;
      reg [3:0] b;
      begin
         b[3] = g[3];
         b[2] = g[3] ^ g[2];
         b[1] = b[2] ^ g[1];
         b[0] = b[1] ^ g[0];
         gray2bin = b;
      end
   endfunction

   function [3:0] bin2gray;
      input [3:0] b;
      begin
         bin2gray = b ^ (b >> 1);
      end
   endfunction

   always @(posedge clk or negedge rst_n) begin
      if (!rst_n) begin
         gray_out <= 4'b0;
         slow <= 1'b1;
      end else begin
         slow <= ~slow;
         if (slow) begin
            bin = gray2bin(gray_out);
            bin = bin + 1'b1;
            gray_out <= bin2gray(bin);
         end
      end
   end

endmodule
