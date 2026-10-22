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
    reg [3:0] sum;
    
    always@(posedge clk or negedge rst) begin
        if(~rst)
            state <= S0;
        else
            state <= nstate;
    end
    
    always@(*) begin
        sum = state + d1 + (d2 ? 2'd2 : 2'd0);
        if (sel == 1'b0) begin
            if (state >= S1_5)
                nstate = S0;
            else if (sum > S3)
                nstate = S3;
            else
                nstate = sum[2:0];
        end
        else begin
            if (state >= S2_5)
                nstate = S0;
            else if (sum > S3)
                nstate = S3;
            else
                nstate = sum[2:0];
        end
    end
    
    always@(posedge clk or negedge rst) begin
        if(~rst) begin
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;
        end
        else begin
            case(state)
                S0, S0_5, S1: begin
                    out1 <= 1'b0;
                    out2 <= 1'b0;
                    out3 <= 1'b0;
                end
                S1_5: begin
                    out1 <= (sel == 1'b0) ? 1'b1 : 1'b0;
                    out2 <= 1'b0;
                    out3 <= 1'b0;
                end
                S2: begin
                    out1 <= (sel == 1'b0) ? 1'b1 : 1'b0;
                    out2 <= 1'b0;
                    out3 <= (sel == 1'b0) ? 1'b1 : 1'b0;
                end
                S2_5: begin
                    if (sel == 1'b0) begin
                        out1 <= 1'b1;
                        out2 <= 1'b0;
                        out3 <= 1'b1;
                    end
                    else begin
                        out1 <= 1'b0;
                        out2 <= 1'b1;
                        out3 <= 1'b0;
                    end
                end
                S3: begin
                    if (sel == 1'b0) begin
                        out1 <= 1'b1;
                        out2 <= 1'b0;
                        out3 <= 1'b1;
                    end
                    else begin
                        out1 <= 1'b0;
                        out2 <= 1'b1;
                        out3 <= 1'b1;
                    end
                end
                default: begin
                    out1 <= 1'b0;
                    out2 <= 1'b0;
                    out3 <= 1'b0;
                end
            endcase
        end
    end
//*************code***********//
endmodule
