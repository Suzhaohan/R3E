module TopModule(
   input   clk,
   input   rst_n,
   output  reg [3:0] gray_out
);

reg [3:0] gray_reg;
reg [3:0] bin_val;
reg count_en;
reg toggle;

// Gray to binary conversion
always @(posedge clk or negedge rst_n) begin
   if(!rst_n) begin
      gray_reg <= 4'b0000;
      bin_val <= 4'b0000;
      count_en <= 1'b0;
      toggle <= 1'b0;
   end
   else begin
      toggle <= ~toggle;
      count_en <= toggle;
      
      if(count_en) begin
         // Gray to binary conversion
         bin_val[3] = gray_reg[3];
         bin_val[2] = gray_reg[2] ^ bin_val[3];
         bin_val[1] = gray_reg[1] ^ bin_val[2];
         bin_val[0] = gray_reg[0] ^ bin_val[1];
         
         // Increment binary
         bin_val <= bin_val + 1'b1;
         
         // Binary to Gray conversion
         gray_reg <= bin_val ^ (bin_val >> 1);
      end
      
      gray_out <= gray_reg;
   end
end

endmodule