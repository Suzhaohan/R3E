module TopModule(
	input wire clk  ,
	input wire rst  ,
	input wire d1 ,
	input wire d2 ,
	input wire sel ,
	
	output reg out1,
	output reg out2,
	output reg out3
);
//*************code***********//

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6;
    reg[2:0] state, nstate;
    reg [3:0] add;
    reg [3:0] next_amount;

    always@(posedge clk or negedge rst) begin
        if(~rst)
            state <= S0;
        else
            state <= nstate;
    end

    always@(*) begin
        // compute add based on both currency inputs
        case ({d1, d2})
            2'b00: add = 0;
            2'b01: add = 2;
            2'b10: add = 1;
            2'b11: add = 3;
            default: add = 0;
        endcase

        next_amount = state + add;
        if (next_amount > S3) next_amount = S3;

        // default: hold
        nstate = state;

        if (sel == 0) begin
            if (state >= S1_5)
                nstate = S0;
            else
                nstate = next_amount;
        end else begin
            if (state >= S2_5)
                nstate = S0;
            else
                nstate = next_amount;
        end
    end

    always @(posedge clk or negedge rst) begin
      if (~rst) begin
        {out1, out2, out3} <= 3'b000;
      end
      else begin
        case (state)
          S0, S0_5, S1:  {out1, out2, out3} <= 3'b000;
          S1_5:          {out1, out2, out3} <= (~sel) ? 3'b100 : 3'b000;
          S2:            {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b000;
          S2_5:          {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b010;
          S3:            {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b011;
          default:        {out1, out2, out3} <= 3'b000;
        endcase
      end
    end
//*************code***********//
endmodule
