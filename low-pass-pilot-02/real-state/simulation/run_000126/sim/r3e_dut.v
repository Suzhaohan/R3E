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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, C1=7, C2=8;
    reg [3:0] state, nstate;
    reg out1_next, out2_next, out3_next;
    
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
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
        nstate = state;
        out1_next = 1'b0;
        out2_next = 1'b0;
        out3_next = 1'b0;
        
        if (state == C1) begin
            out3_next = 1'b1;
            nstate = S0;
        end else if (state == C2) begin
            out3_next = 1'b1;
            nstate = C1;
        end else if (sel == 1'b0 && state >= S1_5) begin
            case (state)
                S1_5: begin out1_next = 1'b1; nstate = S0; end
                S2:   begin out1_next = 1'b1; out3_next = 1'b1; nstate = S0; end
                S2_5: begin out1_next = 1'b1; out3_next = 1'b1; nstate = C1; end
                S3:   begin out1_next = 1'b1; out3_next = 1'b1; nstate = C2; end
                default: nstate = S0;
            endcase
        end else if (sel == 1'b1 && state >= S2_5) begin
            case (state)
                S2_5: begin out2_next = 1'b1; nstate = S0; end
                S3:   begin out2_next = 1'b1; out3_next = 1'b1; nstate = S0; end
                default: nstate = S0;
            endcase
        end else begin
            if (d1 && d2) begin
                if (state <= S3 - 3) nstate = state + 3;
                else nstate = S3;
            end else if (d1) begin
                if (state < S3) nstate = state + 1;
                else nstate = S3;
            end else if (d2) begin
                if (state <= S3 - 2) nstate = state + 2;
                else nstate = S3;
            end else begin
                nstate = state;
            end
        end
    end
//*************code***********//
endmodule
