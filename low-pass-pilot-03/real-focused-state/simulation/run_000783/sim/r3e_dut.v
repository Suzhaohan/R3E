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
    reg d1_reg, d2_reg;

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            d1_reg <= 0;
            d2_reg <= 0;
        end else begin
            state <= nstate;
            d1_reg <= d1;
            d2_reg <= d2;
        end
    end

    always @(*) begin
        if (sel == 0 && state >= S1_5)
            nstate = S0;
        else if (sel == 1 && state >= S2_5)
            nstate = S0;
        else begin
            case (state)
                S0:    nstate = d1_reg ? (d2_reg ? S1_5 : S0_5) : (d2_reg ? S1 : S0);
                S0_5:  nstate = d1_reg ? (d2_reg ? S2 : S1) : (d2_reg ? S1_5 : S0_5);
                S1:    nstate = d1_reg ? (d2_reg ? S2_5 : S1_5) : (d2_reg ? S2 : S1);
                S1_5:  nstate = d1_reg ? (d2_reg ? S3 : S2) : (d2_reg ? S2_5 : S1_5);
                S2:    nstate = d1_reg ? (d2_reg ? S3 : S2_5) : (d2_reg ? S3 : S2);
                S2_5:  nstate = d1_reg ? (d2_reg ? S3 : S3) : (d2_reg ? S3 : S2_5);
                S3:    nstate = S3;
                default: nstate = S0;
            endcase
        end
    end

    always @(*) begin
        if (~rst) begin
            {out1, out2, out3} = 3'b000;
        end else begin
            case (state)
                S0, S0_5, S1: {out1, out2, out3} = 3'b000;
                S1_5        : {out1, out2, out3} = ~sel ? 3'b100 : 3'b000;
                S2          : {out1, out2, out3} = ~sel ? 3'b101 : 3'b000;
                S2_5        : {out1, out2, out3} = ~sel ? 3'b101 : 3'b010;
                S3          : {out1, out2, out3} = ~sel ? 3'b101 : 3'b011;
                default     : {out1, out2, out3} = 3'b000;
            endcase
        end
    end
endmodule
