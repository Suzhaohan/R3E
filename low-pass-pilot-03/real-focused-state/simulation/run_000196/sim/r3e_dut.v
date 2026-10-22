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
    
    always@(posedge clk or negedge rst) begin
        if(~rst)
            state <= S0;
        else
            state <= nstate;
    end
    
    // Purely combinational next-state logic.  Hold value is the CURRENT state
    // (not nstate) to avoid a self-referential latch, and simultaneous d1 & d2
    // deposits are accumulated together (0.5 + 1.0 = 1.5).
    always@(*) begin
        case(state)
            S0     : nstate = (d1 & d2) ? S1_5 :
                              d1       ? S0_5 :
                              d2       ? S1   : S0;
            S0_5   : nstate = (d1 & d2) ? S2   :
                              d1       ? S1   :
                              d2       ? S1_5 : S0_5;
            S1     : nstate = (d1 & d2) ? S2_5 :
                              d1       ? S1_5 :
                              d2       ? S2   : S1;
            S1_5   : nstate = ~sel ? S0 :
                              (d1 & d2) ? S3   :
                              d1        ? S2   :
                              d2        ? S2_5 : S1_5;
            S2     : nstate = ~sel ? S0 :
                              (d1 & d2) ? S3   :
                              d1        ? S2_5 :
                              d2        ? S3   : S2;
            S2_5   : nstate = S0;
            S3     : nstate = S0;
            default: nstate = S0;
        endcase
    end
    
    // Outputs are combinational so they are asserted in the same cycle the
    // dispensing state is entered.
    always @(*) begin
        case (state)
          S1_5:   {out1, out2, out3} = (~sel) ? 3'b100 : 3'b000;
          S2:     {out1, out2, out3} = (~sel) ? 3'b101 : 3'b000;
          S2_5:   {out1, out2, out3} = (~sel) ? 3'b101 : 3'b010;
          S3:     {out1, out2, out3} = (~sel) ? 3'b101 : 3'b011;
          default:{out1, out2, out3} = 3'b000;
        endcase
    end
//*************code***********//
endmodule
