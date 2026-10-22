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
    
    always@(posedge clk or negedge rst) begin
        if(~rst)
            state <= S0;
        else
            state <= nstate;
    end
    
    always@(*) begin
        case(state)
            S0     : nstate = d1? S0_5 : d2? S1 : S0;
            S0_5   : nstate = d1? S1 : d2? S1_5 : S0_5;
            S1     : nstate = d1? S1_5 : d2? S2 : S1;
            S1_5   : nstate = ~sel? S0 : (d1? S2 : d2? S2_5 : S1_5);
            S2     : nstate = ~sel? S0 : (d1? S2_5 : d2? S3 : S2);
            S2_5   : nstate = S0;
            S3     : nstate = S0;
            default: nstate = S0;
        endcase
    end
    
    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        case (state)
            S1_5: begin
                if (~sel) out1 = 1;
            end
            S2: begin
                if (~sel) begin
                    out1 = 1;
                    out3 = 1;
                end
            end
            S2_5: begin
                if (~sel) begin
                    out1 = 1;
                    out3 = 1;
                end else begin
                    out2 = 1;
                end
            end
            S3: begin
                if (~sel) begin
                    out1 = 1;
                    out3 = 1;
                end else begin
                    out2 = 1;
                    out3 = 1;
                end
            end
            default: begin
                out1 = 0;
                out2 = 0;
                out3 = 0;
            end
        endcase
    end
//*************code***********//
endmodule
