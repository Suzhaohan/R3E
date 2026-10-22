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

    wire dispense = (sel == 1'b0 && state >= S1_5) || (sel == 1'b1 && state >= S2_5);
    wire [3:0] sum = state + (d1 ? 1 : 0) + (d2 ? 2 : 0);

    always@(posedge clk or negedge rst) begin
        if(~rst)
            state <= S0;
        else
            state <= nstate;
    end

    always@(*) begin
        if(dispense)
            nstate = S0;
        else if(sum > S3)
            nstate = S3;
        else
            nstate = sum[2:0];
    end

    always@(posedge clk or negedge rst) begin
        if(~rst) begin
            {out1, out2, out3} <= 3'b000;
        end
        else begin
            case(state)
                S0, S0_5, S1: {out1, out2, out3} <= 3'b000;
                S1_5        : {out1, out2, out3} <= sel ? 3'b000 : 3'b100;
                S2          : {out1, out2, out3} <= sel ? 3'b000 : 3'b101;
                S2_5        : {out1, out2, out3} <= sel ? 3'b010 : 3'b101;
                S3          : {out1, out2, out3} <= sel ? 3'b011 : 3'b101;
                default     : {out1, out2, out3} <= 3'b000;
            endcase
        end
    end
//*************code***********//
endmodule
