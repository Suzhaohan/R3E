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

    localparam S0   = 3'd0,
               S0_5 = 3'd1,
               S1   = 3'd2,
               S1_5 = 3'd3,
               S2   = 3'd4,
               S2_5 = 3'd5,
               S3   = 3'd6;

    reg [2:0] state, nstate;

    // State register
    always @(posedge clk or negedge rst) begin
        if (~rst)
            state <= S0;
        else
            state <= nstate;
    end

    // Next-state logic (complete; no latch)
    always @(*) begin
        case (state)
            S0   : nstate = d1 ? S0_5 : d2 ? S1   : S0;
            S0_5 : nstate = d1 ? S1   : d2 ? S1_5 : S0_5;
            S1   : nstate = d1 ? S1_5 : d2 ? S2   : S1;
            S1_5 : nstate = ~sel ? S0 : d1 ? S2 : d2 ? S2_5 : S1_5;
            S2   : nstate = ~sel ? S0 : d1 ? S2_5 : d2 ? S3 : S2;
            S2_5 : nstate = S0;
            S3   : nstate = S0;
            default: nstate = S0;
        endcase
    end

    // Output logic
    always @(*) begin
        case (state)
            S1_5 : {out1, out2, out3} = ~sel ? 3'b100 : 3'b000;
            S2   : {out1, out2, out3} = ~sel ? 3'b101 : 3'b000;
            S2_5 : {out1, out2, out3} = ~sel ? 3'b101 : 3'b010;
            S3   : {out1, out2, out3} = ~sel ? 3'b101 : 3'b011;
            default: {out1, out2, out3} = 3'b000;
        endcase
    end
//*************code***********//
endmodule
