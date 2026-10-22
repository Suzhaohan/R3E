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

    parameter S0=4'd0, S0_5=4'd1, S1=4'd2, S1_5=4'd3, S2=4'd4, S2_5=4'd5, S3=4'd6, C1=4'd7, C2=4'd8;
    reg [3:0] state, nstate;
    reg out1_next, out2_next, out3_next;

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;
        end else begin
            state <= nstate;
            out1 <= out1_next;
            out2 <= out2_next;
            out3 <= out3_next;
        end
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
                if (~sel) nstate = S0;
                else if (d1) nstate = S2;
                else if (d2) nstate = S2_5;
                else nstate = S1_5;
            end
            S2: begin
                if (~sel) nstate = S0;
                else if (d1) nstate = S2_5;
                else if (d2) nstate = S3;
                else nstate = S2;
            end
            S2_5: begin
                if (~sel) nstate = C1;
                else nstate = S0;
            end
            S3: begin
                if (~sel) nstate = C2;
                else nstate = S0;
            end
            C1: nstate = S0;
            C2: nstate = C1;
            default: nstate = S0;
        endcase
    end

    always @(*) begin
        out1_next = 1'b0;
        out2_next = 1'b0;
        out3_next = 1'b0;
        case (state)
            S0, S0_5, S1: begin end
            S1_5: begin
                if (~sel) out1_next = 1'b1;
            end
            S2: begin
                if (~sel) begin
                    out1_next = 1'b1;
                    out3_next = 1'b1;
                end
            end
            S2_5: begin
                if (~sel) begin
                    out1_next = 1'b1;
                    out3_next = 1'b1;
                end else begin
                    out2_next = 1'b1;
                end
            end
            S3: begin
                if (~sel) begin
                    out1_next = 1'b1;
                    out3_next = 1'b1;
                end else begin
                    out2_next = 1'b1;
                    out3_next = 1'b1;
                end
            end
            C1: begin
                out3_next = 1'b1;
            end
            C2: begin
                out3_next = 1'b1;
            end
            default: begin end
        endcase
    end

endmodule
