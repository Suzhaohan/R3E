module TopModule(
   input   clk,
   input   rst_n,

   output  reg [3:0] gray_out
);
   reg phase;
   wire [3:0] gray_wire;
   wire [3:0] bin;
   wire [3:0] bin_inc;
   wire [3:0] gray_next;

   // Internal wire for current Gray code value
   assign gray_wire = gray_out;

   // Gray to binary conversion
   assign bin[3] = gray_wire[3];
   assign bin[2] = gray_wire[2] ^ bin[3];
   assign bin[1] = gray_wire[1] ^ bin[2];
   assign bin[0] = gray_wire[0] ^ bin[1];

   // Increment binary value
   assign bin_inc = bin + 4'b0001;

   // Binary to Gray conversion
   assign gray_next = bin_inc ^ (bin_inc >> 1);

   // Update counter every two clock cycles
   always @(posedge clk or negedge rst_n) begin
      if (!rst_n) begin
         gray_out <= 4'b0000;
         phase <= 1'b0;
      end else begin
         phase <= ~phase;
         if (phase)
            gray_out <= gray_next;
      end
   end
endmodule
