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
    reg [3:0] next_amount;

    always @(*) begin
        nstate = state;
        if ( (sel == 1'b0 && state >= S1_5) || (sel == 1'b1 && state >= S2_5) ) begin
            nstate = S0;
        end else begin
            next_amount = state + d1 + 2*d2;
            if (next_amount >= S3)
                nstate = S3;
            else
                nstate = next_amount[2:0];
        end
    end

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= S0;
            {out1, out2, out3} <= 3'b000;
        end else begin
            state <= nstate;
            case (state)
                S1_5: {out1, out2, out3} <= (sel == 1'b0) ? 3'b100 : 3'b000;
                S2:   {out1, out2, out3} <= (sel == 1'b0) ? 3'b101 : 3'b000;
                S2_5: {out1, out2, out3} <= (sel == 1'b0) ? 3'b101 : 3'b010;
                S3:   {out1, out2, out3} <= (sel == 1'b0) ? 3'b101 : 3'b011;
                default: {out1, out2, out3} <= 3'b000;
            endcase
        end
    end

//*************code***********//
endmodule
