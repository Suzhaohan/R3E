module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);
   reg  [3:0] bin_count;
   reg        toggle;

   wire [3:0] bin_next;
   wire [3:0] gray_next;

   assign bin_next  = bin_count + 4'b0001;
   assign gray_next = bin_next ^ (bin_next >> 1);

   always @(posedge clk or negedge rst_n) begin
      if (rst_n == 1'b0) begin
         bin_count <= 4'b0000;
         toggle    <= 1'b0;
         gray_out  <= 4'b0000;
      end
      else begin
         toggle <= ~toggle;
         if (toggle) begin
            bin_count <= bin_next;
            gray_out  <= gray_next;
         end
      end
   end
endmodule
