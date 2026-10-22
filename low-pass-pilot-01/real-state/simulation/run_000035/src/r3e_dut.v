module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);
   reg  [3:0] bin_out;
   reg  [3:0] bin_add_wire;
   wire [3:0] gray_wire;
   wire [3:0] bin_from_gray;

   assign bin_from_gray[3] = gray_wire[3];
   assign bin_from_gray[2] = gray_wire[2] ^ bin_from_gray[3];
   assign bin_from_gray[1] = gray_wire[1] ^ bin_from_gray[2];
   assign bin_from_gray[0] = gray_wire[0] ^ bin_from_gray[1];

   assign gray_wire = bin_add_wire ^ (bin_add_wire >> 1);

   always @(posedge clk or negedge rst_n) begin
      if (rst_n == 1'b0) begin
         bin_out        <= 4'b0;
         bin_add_wire   <= 4'b0;
         gray_out       <= 4'b0;
      end else begin
         bin_out        <= bin_from_gray;
         bin_add_wire   <= bin_out + 1'b1;
         gray_out       <= gray_wire;
      end
   end
endmodule