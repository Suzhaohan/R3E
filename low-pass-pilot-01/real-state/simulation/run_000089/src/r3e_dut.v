module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);

reg  [3:0] bin_count;
reg        div2;

wire [3:0] next_bin  = bin_count + 4'd1;
wire [3:0] next_gray = next_bin ^ (next_bin >> 1);

always @(posedge clk or negedge rst_n) begin
   if (!rst_n) begin
      bin_count <= 4'd0;
      gray_out  <= 4'd0;
      div2      <= 1'b0;
   end
   else if (div2) begin
      bin_count <= next_bin;
      gray_out  <= next_gray;
      div2      <= 1'b0;
   end
   else begin
      div2 <= 1'b1;
   end
end

endmodule
