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
    reg [2:0] state;

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= S0;
            {out1, out2, out3} <= 3'b000;
        end else begin
            // State transition (sequential, so d1/d2 are sampled only at clock edge)
            case(state)
                S0: begin
                    if (d1) state <= S0_5;
                    else if (d2) state <= S1;
                end
                S0_5: begin
                    if (d1) state <= S1;
                    else if (d2) state <= S1_5;
                end
                S1: begin
                    if (d1) state <= S1_5;
                    else if (d2) state <= S2;
                end
                S1_5: begin
                    if (!sel) state <= S0;
                    else if (d1) state <= S2;
                    else if (d2) state <= S2_5;
                end
                S2: begin
                    if (!sel) state <= S0;
                    else if (d1) state <= S2_5;
                    else if (d2) state <= S3;
                end
                S2_5: state <= S0;
                S3:   state <= S0;
                default: state <= S0;
            endcase

            // Output logic (registered)
            case(state)
                S0, S0_5, S1: {out1, out2, out3} <= 3'b000;
                S1_5:         {out1, out2, out3} <= (~sel) ? 3'b100 : 3'b000;
                S2:           {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b000;
                S2_5:         {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b010;
                S3:           {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b011;
                default:      {out1, out2, out3} <= 3'b000;
            endcase
        end
    end
endmodule
