module TopModule(
  input wire clk,
  input wire rst,
  input wire d1,
  input wire d2,
  input wire sel,
  output reg out1,
  output reg out2,
  output reg out3
);

  localparam ACCUM = 2'b00,
             DISP_BEV1 = 2'b01,
             DISP_BEV2 = 2'b10,
             DISP_CHG = 2'b11;

  reg [1:0] state, next_state;
  reg [4:0] amount, next_amount;
  reg [4:0] change, next_change;

  always @(*) begin
    next_state = state;
    next_amount = amount;
    next_change = change;

    case (state)
      ACCUM: begin
        if (d1) next_amount = next_amount + 5'd1;
        if (d2) next_amount = next_amount + 5'd2;
        if (next_amount >= (sel ? 5'd5 : 5'd3)) begin
          next_change = next_amount - (sel ? 5'd5 : 5'd3);
          next_amount = 5'd0;
          next_state = sel ? DISP_BEV2 : DISP_BEV1;
        end
      end
      DISP_BEV1: begin
        if (change > 0) begin
          if (change > 1) begin
            next_change = change - 5'd1;
            next_state = DISP_CHG;
          end else begin
            next_change = 5'd0;
            next_state = ACCUM;
          end
        end else begin
          next_state = ACCUM;
        end
      end
      DISP_BEV2: begin
        if (change > 0) begin
          if (change > 1) begin
            next_change = change - 5'd1;
            next_state = DISP_CHG;
          end else begin
            next_change = 5'd0;
            next_state = ACCUM;
          end
        end else begin
          next_state = ACCUM;
        end
      end
      DISP_CHG: begin
        if (change > 1) begin
          next_change = change - 5'd1;
          next_state = DISP_CHG;
        end else begin
          next_change = 5'd0;
          next_state = ACCUM;
        end
      end
      default: next_state = ACCUM;
    endcase
  end

  always @(posedge clk or negedge rst) begin
    if (~rst) begin
      state <= ACCUM;
      amount <= 5'd0;
      change <= 5'd0;
      out1 <= 1'b0;
      out2 <= 1'b0;
      out3 <= 1'b0;
    end else begin
      state <= next_state;
      amount <= next_amount;
      change <= next_change;

      out1 <= (state == DISP_BEV1);
      out2 <= (state == DISP_BEV2);
      out3 <= (state == DISP_CHG) || 
              ((state == DISP_BEV1 || state == DISP_BEV2) && (change > 0));
    end
  end

endmodule
