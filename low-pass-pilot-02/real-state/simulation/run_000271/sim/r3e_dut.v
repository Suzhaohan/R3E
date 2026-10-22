module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);

reg [3:0] bin_cnt;
reg toggle;

always @(posedge clk or negedge rst_n) begin
   if (rst_n == 1'b0) begin
      bin_cnt <= 4'b0;
      gray_out <= 4'b0;
      toggle <= 1'b0;
   end
   else begin
      if (toggle == 1'b0) begin
         bin_cnt <= bin_cnt + 1'b1;
         gray_out <= (bin_cnt + 1'b1) ^ ((bin_cnt + 1'b1) >> 1);
      end
      toggle <= ~toggle;
   end
end

endmodule
