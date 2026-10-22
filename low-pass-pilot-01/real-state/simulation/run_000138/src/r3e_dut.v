module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);

reg phase;
wire [3:0] gray_curr;
wire [3:0] bin_curr;
wire [3:0] bin_next;
wire [3:0] gray_next;

assign gray_curr = gray_out;

// Gray code to binary conversion
assign bin_curr[3] = gray_curr[3];
assign bin_curr[2] = gray_curr[2] ^ bin_curr[3];
assign bin_curr[1] = gray_curr[1] ^ bin_curr[2];
assign bin_curr[0] = gray_curr[0] ^ bin_curr[1];

// Binary increment
assign bin_next = bin_curr + 4'b0001;

// Binary to Gray code conversion
assign gray_next = bin_next ^ (bin_next >> 1);

always @(posedge clk or negedge rst_n) begin
   if (rst_n == 1'b0) begin
      gray_out <= 4'b0000;
      phase <= 1'b0;
   end
   else begin
      phase <= ~phase;
      if (phase)
         gray_out <= gray_next;
   end
end

endmodule
