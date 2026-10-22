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
    reg d1_r, d2_r;

    // Combinational edge detect: one-shot pulse per currency input
    wire d1_p = d1 & ~d1_r;
    wire d2_p = d2 & ~d2_r;

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            d1_r  <= 1'b0;
            d2_r  <= 1'b0;
        end
        else begin
            state <= nstate;
            d1_r  <= d1;
            d2_r  <= d2;
        end
    end

    always @(*) begin
        case (state)
            S0   : nstate = d1_p ? S0_5 : d2_p ? S1   : S0;
            S0_5 : nstate = d1_p ? S1   : d2_p ? S1_5 : S0_5;
            S1   : nstate = d1_p ? S1_5 : d2_p ? S2   : S1;
            S1_5 : nstate = ~sel ? S0   : d1_p ? S2   : d2_p ? S2_5 : S1_5;
            S2   : nstate = ~sel ? S0   : d1_p ? S2_5 : d2_p ? S3   : S2;
            default: nstate = S0;
        endcase
    end

    // Moore outputs: combinational, derived from the CURRENT state
    always @(*) begin
        case (state)
            S1_5 : {out1, out2, out3} = (~sel) ? 3'b100 : 3'b000;
            S2   : {out1, out2, out3} = (~sel) ? 3'b101 : 3'b000;
            S2_5 : {out1, out2, out3} = (~sel) ? 3'b101 : 3'b010;
            S3   : {out1, out2, out3} = (~sel) ? 3'b101 : 3'b011;
            default: {out1, out2, out3} = 3'b000;
        endcase
    end
//*************code***********//
endmodule
