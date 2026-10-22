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
    reg d1_pulse, d2_pulse;
    reg [3:0] add;

    always @(posedge clk or negedge rst) begin
        if(!rst) begin
            d1_r <= 0;
            d2_r <= 0;
            d1_pulse <= 0;
            d2_pulse <= 0;
        end else begin
            d1_r <= d1;
            d2_r <= d2;
            d1_pulse <= d1 & ~d1_r;
            d2_pulse <= d2 & ~d2_r;
        end
    end

    always @(posedge clk or negedge rst) begin
        if(!rst)
            state <= S0;
        else
            state <= nstate;
    end

    always @(*) begin
        add = 0;
        if (d1_pulse) add = add + 1;
        if (d2_pulse) add = add + 2;

        if ( (sel == 0 && state >= S1_5) || (sel == 1 && state >= S2_5) ) begin
            nstate = S0;
        end else begin
            nstate = state + add;
            if (nstate > S3) nstate = S3;
        end
    end

    always @(*) begin
        if(!rst) begin
            {out1, out2, out3} = 3'b000;
        end else begin
            case(state)
                S0, S0_5, S1: {out1, out2, out3} = 3'b000;
                S1_5        : {out1, out2, out3} = sel ? 3'b000 : 3'b100;
                S2          : {out1, out2, out3} = sel ? 3'b000 : 3'b101;
                S2_5        : {out1, out2, out3} = sel ? 3'b010 : 3'b101;
                S3          : {out1, out2, out3} = sel ? 3'b011 : 3'b101;
                default     : {out1, out2, out3} = 3'b000;
            endcase
        end
    end
//*************code***********//
endmodule
