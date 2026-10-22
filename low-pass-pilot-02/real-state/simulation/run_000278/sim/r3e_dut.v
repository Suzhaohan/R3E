module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);

   wire [3:0] gray_to_bin;
   wire [3:0] bin_inc;
   wire [3:0] next_gray;
   reg        phase;

   // Gray code to binary conversion
   assign gray_to_bin[3] = gray_out[3];
   assign gray_to_bin[2] = gray_out[2] ^ gray_to_bin[3];
   assign gray_to_bin[1] = gray_out[1] ^ gray_to_bin[2];
   assign gray_to_bin[0] = gray_out[0] ^ gray_to_bin[1];

   // Binary increment
   assign bin_inc = gray_to_bin + 4'b0001;

   // Binary to Gray code conversion
   assign next_gray = bin_inc ^ (bin_inc >> 1);

   // Update the Gray code output every two clock cycles
   always @(posedge clk or negedge rst_n) begin
      if (rst_n == 1'b0) begin
         gray_out <= 4'b0000;
         phase    <= 1'b0;
      end
      else begin
         if (phase) begin
            gray_out <= next_gray;
            phase    <= 1'b0;
         end
         else begin
            phase <= 1'b1;
         end
      end
   end

endmodule
