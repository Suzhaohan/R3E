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
    reg [2:0] state, nstate;

    always@(posedge clk or negedge rst) begin
        if(~rst)
            state <= S0;
        else
            state <= nstate;
    end

    // Next-state logic: no self-referential latch; every branch
    // explicitly holds the current state when no coin is inserted.
    always@(*) begin
        case(state)
            S0   : nstate = d1? S0_5 :
                            d2? S1   : S0;
            S0_5 : nstate = d1? S1   :
                            d2? S1_5 : S0_5;
            S1   : nstate = d1? S1_5 :
                            d2? S2   : S1;
            S1_5 : nstate = ~sel? S0  :
                            d1? S2   :
                            d2? S2_5 : S1_5;
            S2   : nstate = ~sel? S0  :
                            d1? S2_5 :
                            d2? S3   : S2;
            S2_5 : nstate = S0;
            S3   : nstate = S0;
            default: nstate = S0;
        endcase
    end

    // Moore output logic: added the missing S0_5 / S1_5 cases and removed
    // the duplicated S2 case label (the second S2 branch was dead code).
    always@(*) begin
        case(state)
            S0, S0_5, S1 : {out1, out2, out3} = 3'b000;
            S1_5         : {out1, out2, out3} = sel? 3'b000 : 3'b100;
            S2           : {out1, out2, out3} = sel? 3'b000 : 3'b101;
            S2_5         : {out1, out2, out3} = sel? 3'b010 : 3'b101;
            S3           : {out1, out2, out3} = sel? 3'b011 : 3'b101;
            default      : {out1, out2, out3} = 3'b000;
        endcase
    end
//*************code***********//
endmodule
