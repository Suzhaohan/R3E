module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);

reg phase;
wire [3:0] bin_from_gray;
wire [3:0] bin_plus_one;
wire [3:0] gray_next;

assign bin_from_gray[3] = gray_out[3];
assign bin_from_gray[2] = gray_out[2] ^ bin_from_gray[3];
assign bin_from_gray[1] = gray_out[1] ^ bin_from_gray[2];
assign bin_from_gray[0] = gray_out[0] ^ bin_from_gray[1];

assign bin_plus_one = bin_from_gray + 4'b0001;
assign gray_next = (bin_plus_one >> 1) ^ bin_plus_one;

always @(posedge clk or negedge rst_n) begin
   if (rst_n == 1'b0) begin
      gray_out <= 4'b0000;
      phase <= 1'b0;
   end
   else begin
      if (phase == 1'b1) begin
         gray_out <= gray_next;
      end
      phase <= ~phase;
   end
end

endmodule
