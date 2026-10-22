module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);

reg  [3:0] bin_cnt;
reg        phase;

wire [3:0] bin_next = (phase == 1'b0) ? (bin_cnt + 1'b1) : bin_cnt;

always @(posedge clk or negedge rst_n) begin
   if (rst_n == 1'b0) begin
      bin_cnt  <= 4'b0;
      phase    <= 1'b0;
      gray_out <= 4'b0;
   end else begin
      bin_cnt  <= bin_next;
      phase    <= ~phase;
      gray_out <= bin_next ^ (bin_next >> 1);
   end
end

endmodule
