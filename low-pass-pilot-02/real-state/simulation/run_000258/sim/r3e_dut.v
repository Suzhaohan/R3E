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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6;
    reg [2:0] state, nstate;

    // state register
    always@(posedge clk or negedge rst) begin
        if(!rst)
            state <= S0;
        else
            state <= nstate;
    end

    // next-state logic (accumulate 0.5/1 yuan, then dispense according to sel)
    always@(*) begin
        case(state)
            S0   : nstate = d1 ? S0_5 : (d2 ? S1   : S0);
            S0_5 : nstate = d1 ? S1   : (d2 ? S1_5 : S0_5);
            S1   : nstate = d1 ? S1_5 : (d2 ? S2   : S1);
            // 1.5 yuan: beverage 1 affordable -> dispense; else keep accumulating
            S1_5 : nstate = ~sel ? S0 : (d1 ? S2 : (d2 ? S2_5 : S1_5));
            // 2.0 yuan: beverage 1 affordable -> dispense; else keep accumulating
            S2   : nstate = ~sel ? S0 : (d1 ? S2_5 : (d2 ? S3 : S2));
            // 2.5 / 3.0 yuan: always dispense and return to zero
            S2_5 : nstate = S0;
            S3   : nstate = S0;
            default: nstate = S0;
        endcase
    end

    // combinational output logic
    always@(*) begin
        case(state)
            S1_5 : {out1, out2, out3} = ~sel ? 3'b100 : 3'b000; // bev1, no change
            S2   : {out1, out2, out3} = ~sel ? 3'b101 : 3'b000; // bev1 + 0.5 change
            S2_5 : {out1, out2, out3} = ~sel ? 3'b101 : 3'b010; // bev1+change / bev2
            S3   : {out1, out2, out3} = ~sel ? 3'b101 : 3'b011; // bev1+change / bev2+change
            default: {out1, out2, out3} = 3'b000;
        endcase
    end
endmodule
