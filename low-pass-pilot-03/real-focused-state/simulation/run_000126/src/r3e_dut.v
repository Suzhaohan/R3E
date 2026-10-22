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

    localparam S0      = 4'd0,
               S0_5    = 4'd1,
               S1      = 4'd2,
               S1_5    = 4'd3,
               S2      = 4'd4,
               S2_5    = 4'd5,
               S3      = 4'd6,
               CHANGE1 = 4'd7,
               CHANGE2 = 4'd8;

    reg [3:0] state, nstate;

    always @(posedge clk or negedge rst) begin
        if (!rst)
            state <= S0;
        else
            state <= nstate;
    end

    always @(*) begin
        case (state)
            S0: begin
                if (d1) nstate = S0_5;
                else if (d2) nstate = S1;
                else nstate = S0;
            end
            S0_5: begin
                if (d1) nstate = S1;
                else if (d2) nstate = S1_5;
                else nstate = S0_5;
            end
            S1: begin
                if (d1) nstate = S1_5;
                else if (d2) nstate = S2;
                else nstate = S1;
            end
            S1_5: begin
                if (!sel) nstate = S0;
                else begin
                    if (d1) nstate = S2;
                    else if (d2) nstate = S2_5;
                    else nstate = S1_5;
                end
            end
            S2: begin
                if (!sel) nstate = S0;
                else begin
                    if (d1) nstate = S2_5;
                    else if (d2) nstate = S3;
                    else nstate = S2;
                end
            end
            S2_5: begin
                if (sel) nstate = S0;
                else nstate = CHANGE1;
            end
            S3: begin
                if (sel) nstate = S0;
                else nstate = CHANGE2;
            end
            CHANGE1: nstate = S0;
            CHANGE2: nstate = CHANGE1;
            default: nstate = S0;
        endcase
    end

    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        case (state)
            S0, S0_5, S1: begin
                out1 = 0; out2 = 0; out3 = 0;
            end
            S1_5: begin
                if (!sel) out1 = 1;
            end
            S2: begin
                if (!sel) begin
                    out1 = 1;
                    out3 = 1;
                end
            end
            S2_5: begin
                if (!sel) begin
                    out1 = 1;
                    out3 = 1;
                end else begin
                    out2 = 1;
                end
            end
            S3: begin
                if (!sel) begin
                    out1 = 1;
                    out3 = 1;
                end else begin
                    out2 = 1;
                    out3 = 1;
                end
            end
            CHANGE1, CHANGE2: begin
                out3 = 1;
            end
            default: begin
                out1 = 0; out2 = 0; out3 = 0;
            end
        endcase
    end
//*************code***********//
endmodule
