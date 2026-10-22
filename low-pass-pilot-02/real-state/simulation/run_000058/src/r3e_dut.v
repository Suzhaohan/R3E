module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);
reg  [3:0] bin_cnt;
reg        phase;
wire [3:0] bin_next;
wire [3:0] gray_next;

assign bin_next  = bin_cnt + 1'b1;
assign gray_next = bin_next ^ (bin_next >> 1);

always @(posedge clk or negedge rst_n) begin
   if(rst_n == 1'b0) begin
      bin_cnt  <= 4'b0;
      phase    <= 1'b0;
      gray_out <= 4'b0;
   end
   else begin
      phase <= ~phase;
      if(phase) begin
         bin_cnt  <= bin_next;
         gray_out <= gray_next;
      end
   end
end
endmodule
