module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);
//Gray code to binary conversion
reg  [3:0] bin_out;
reg  [3:0] bin_add_wire;
wire [3:0] gray_wire;
wire [3:0] bin_next;

assign bin_next[3] = gray_wire[3];
assign bin_next[2] = gray_wire[2] ^ bin_next[3];
assign bin_next[1] = gray_wire[1] ^ bin_next[2];
assign bin_next[0] = gray_wire[0] ^ bin_next[1];

always @(posedge clk or negedge rst_n) begin
   if (rst_n == 1'b0) begin
      bin_out <= 4'b0;
   end
   else begin
      bin_out <= bin_next;
   end
end

//Binary increment
always @(posedge clk or negedge rst_n) begin
   if (rst_n == 1'b0) begin
      bin_add_wire <= 4'b0;
   end
   else begin
      bin_add_wire <= bin_out + 1'b1;
   end
end

//Binary to gray code conversion
assign gray_wire = (bin_add_wire >> 1) ^ bin_add_wire;

always @(posedge clk or negedge rst_n) begin
   if (rst_n == 1'b0) begin
      gray_out <= 4'b0;
   end
   else begin
      gray_out <= gray_wire;
   end
end
endmodule
