module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);

reg [3:0] bin_reg;
reg phase;

wire [3:0] bin_next = bin_reg + 1'b1;
wire [3:0] gray_next = bin_next ^ (bin_next >> 1);

always @(posedge clk or negedge rst_n) begin
   if (!rst_n) begin
      bin_reg <= 4'b0;
      phase <= 1'b0;
      gray_out <= 4'b0;
   end else begin
      if (phase) begin
         bin_reg <= bin_next;
         gray_out <= gray_next;
         phase <= 1'b0;
      end else begin
         phase <= 1'b1;
      end
   end
end

endmodule
