module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);

   reg [3:0] bin;
   reg phase;

   always @(posedge clk or negedge rst_n) begin
      if (rst_n == 1'b0) begin
         bin <= 4'b0;
         phase <= 1'b0;
         gray_out <= 4'b0;
      end
      else begin
         if (phase == 1'b0) begin
            phase <= 1'b1;
         end
         else begin
            phase <= 1'b0;
            bin <= bin + 1'b1;
         end
         gray_out <= bin ^ (bin >> 1);
      end
   end

endmodule