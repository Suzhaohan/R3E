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
    reg d1_r, d2_r;
    wire d1_pulse = d1 & ~d1_r;
    wire d2_pulse = d2 & ~d2_r;
    
    always@(posedge clk or negedge rst) begin
        if(~rst) begin
            state <= 0;
            d1_r <= 0;
            d2_r <= 0;
        end else begin
            state <= nstate;
            d1_r <= d1;
            d2_r <= d2;
        end
    end
    
    always@(*) begin
        case(state)
            S0     : nstate = d1_pulse ? S0_5 :
                              d2_pulse ? S1 :
                              S0;
            S0_5   : nstate = d1_pulse ? S1 :
                              d2_pulse ? S1_5 :
                              S0_5;
            S1     : nstate = d1_pulse ? S1_5 :
                              d2_pulse ? S2 :
                              S1;
            S1_5   : nstate = ~sel ? S0 :
                              d1_pulse ? S2 :
                              d2_pulse ? S2_5 :
                              S1_5;
            S2     : nstate = ~sel ? S0 :
                              d1_pulse ? S2_5 :
                              d2_pulse ? S3 :
                              S2;
            S2_5   : nstate = ~sel ? S0 :
                              d1_pulse ? S3 :
                              d2_pulse ? S3 :
                              S2_5;
            S3     : nstate = ~sel ? S0 :
                              S3;
            default: nstate = S0;
        endcase
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
