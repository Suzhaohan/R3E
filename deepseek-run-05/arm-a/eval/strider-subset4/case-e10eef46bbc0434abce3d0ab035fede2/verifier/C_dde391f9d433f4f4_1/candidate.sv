module lshift_reg (input             clk,        // Clock input
                   input            rstn,        // Active low reset input
                   input [7:0]       load_val,   // Load value 
                   input             load_en,     // Load enable
                   output reg [7:0] op);         // Output register value
 
   integer i;
 
   // At posedge of clock, if reset is low set output to 0
   // If reset is high, load new value to op if load_en=1
   // If reset is high, and load_en=0 shift register to left
   always @ (posedge clk) begin
      if (!rstn) begin
        op = 0;
      end else begin
 
        // If load_en is 1, load the value to op
        // else keep shifting for every clock
        if (load_en) begin
          op = load_val;
        end else begin
            for (i = 7; i > 0; i = i - 1) begin
              op[i] = op[i-1];
            end
            op[0] = 1'b0;
        end
      end
    end
endmodule
 
