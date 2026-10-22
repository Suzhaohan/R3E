module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);

reg [3:0] gray_reg;
reg slow;

wire [3:0] bin_curr;
wire [3:0] bin_next;
wire [3:0] gray_next;

// Gray to binary conversion
assign bin_curr[3] = gray_reg[3];
assign bin_curr[2] = bin_curr[3] ^ gray_reg[2];
assign bin_curr[1] = bin_curr[2] ^ gray_reg[1];
assign bin_curr[0] = bin_curr[1] ^ gray_reg[0];

// Increment binary value
assign bin_next = bin_curr + 1'b1;

// Binary to Gray conversion
assign gray_next = (bin_next >> 1) ^ bin_next;

always @(posedge clk or negedge rst_n) begin
   if (!rst_n) begin
      gray_reg <= 4'b0;
      gray_out <= 4'b0;
      slow <= 1'b0;
   end
   else begin
      if (slow) begin
         gray_reg <= gray_next;
         gray_out <= gray_next;
         slow <= 1'b0;
      end
      else begin
         slow <= 1'b1;
      end
   end
end

endmodule