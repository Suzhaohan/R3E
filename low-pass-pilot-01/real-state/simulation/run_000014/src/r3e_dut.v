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

    // Edge detection
    reg d1_prev, d2_prev;
    wire d1_pulse = d1 & ~d1_prev;
    wire d2_pulse = d2 & ~d2_prev;

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, CHG1=7, CHG2=8;
    reg[3:0] state, nstate;
    
    always@(posedge clk or negedge rst) begin
        if(~rst) begin
            d1_prev <= 0;
            d2_prev <= 0;
            state <= S0;
        end else begin
            d1_prev <= d1;
            d2_prev <= d2;
            state <= nstate;
        end
    end
    
    always@(*) begin
        nstate = state;
        case(state)
            S0     : nstate = d1_pulse? S0_5:
                              d2_pulse? S1:
                              state;
            S0_5   : nstate = d1_pulse? S1:
                              d2_pulse? S1_5:
                              state;
            S1     : nstate = d1_pulse? S1_5:
                              d2_pulse? S2:
                              state;
            S1_5   : nstate = ~sel? S0:
                              d1_pulse? S2:
                              d2_pulse? S2_5:
                              state;
            S2     : nstate = ~sel? S0:
                              d1_pulse? S2_5:
                              d2_pulse? S3:
                              state;
            S2_5   : nstate = ~sel? CHG1:
                              S0; // sel=1: dispense beverage 2, no change
            S3     : nstate = ~sel? CHG2:
                              S0; // sel=1: dispense beverage 2 + 0.5 change
            CHG1   : nstate = S0;
            CHG2   : nstate = CHG1;
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
          CHG1:          {out1, out2, out3} <= 3'b001;
          CHG2:          {out1, out2, out3} <= 3'b001;
          default:       {out1, out2, out3} <= 3'b000;
        endcase
      end
    end
//*************code***********//
endmodule
