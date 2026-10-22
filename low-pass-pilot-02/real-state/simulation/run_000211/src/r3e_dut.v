module TopModule (
   input  clk,
   input  rst_n,
   output reg [3:0] gray_out
);

   reg [3:0] bin;
   reg       phase;

   wire [3:0] bin_next  = phase ? (bin + 1'b1) : bin;
   wire [3:0] gray_next = bin_next ^ (bin_next >> 1);

   always @(posedge clk or negedge rst_n) begin
      if (!rst_n) begin
         bin      <= 4'b0000;
         phase    <= 1'b0;
         gray_out <= 4'b0000;
      end
      else begin
         bin      <= bin_next;
         phase    <= ~phase;
         gray_out <= gray_next;
      end
   end

endmodule
