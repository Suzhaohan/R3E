module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);

reg  [3:0] bin;
reg        phase;
wire [3:0] next_bin;
wire [3:0] next_gray;

assign next_bin  = bin + 1'b1;
assign next_gray = next_bin ^ (next_bin >> 1);

always @(posedge clk or negedge rst_n) begin
   if (!rst_n) begin
      bin      <= 4'b0;
      phase    <= 1'b0;
      gray_out <= 4'b0;
   end
   else begin
      phase <= ~phase;
      if (phase) begin
         bin      <= next_bin;
         gray_out <= next_gray;
      end
   end
end

endmodule
