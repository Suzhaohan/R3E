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

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            {out1, out2, out3} <= 3'b000;
        end else begin
            state <= nstate;
            out1 <= (state == S1_5 && !sel) || (state == S2 && !sel) || (state == S2_5 && !sel) || (state == S3 && !sel);
            out2 <= (state == S2_5 && sel) || (state == S3 && sel);
            out3 <= (state == S2 && !sel) || (state == S2_5 && !sel) || (state == S3);
        end
    end

    always @(*) begin
        case(state)
            S0: begin
                if (d1 && d2) nstate = S1_5;
                else if (d1) nstate = S0_5;
                else if (d2) nstate = S1;
                else nstate = S0;
            end
            S0_5: begin
                if (d1 && d2) nstate = S2;
                else if (d1) nstate = S1;
                else if (d2) nstate = S1_5;
                else nstate = S0_5;
            end
            S1: begin
                if (d1 && d2) nstate = S2_5;
                else if (d1) nstate = S1_5;
                else if (d2) nstate = S2;
                else nstate = S1;
            end
            S1_5: begin
                if (!sel) nstate = S0;
                else begin
                    if (d1 && d2) nstate = S3;
                    else if (d1) nstate = S2;
                    else if (d2) nstate = S2_5;
                    else nstate = S1_5;
                end
            end
            S2: begin
                if (!sel) nstate = S0;
                else begin
                    if (d1 && d2) nstate = S3;
                    else if (d1) nstate = S2_5;
                    else if (d2) nstate = S3;
                    else nstate = S2;
                end
            end
            S2_5: nstate = S0;
            S3: nstate = S0;
            default: nstate = S0;
        endcase
    end

endmodule
