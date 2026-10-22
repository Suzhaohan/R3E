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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, S_CHANGE=7;
    reg[2:0] state, nstate;
    reg[1:0] change, nchange;
    reg[2:0] total_change;
    
    always@(posedge clk or negedge rst) begin
        if(~rst) begin
            state <= S0;
            change <= 0;
        end else begin
            state <= nstate;
            change <= nchange;
        end
    end
    
    always@(*) begin
        nstate = state;
        nchange = change;
        out1 = 0;
        out2 = 0;
        out3 = 0;
        total_change = 0;
        
        case(state)
            S0, S0_5, S1, S1_5, S2, S2_5, S3: begin
                if((sel == 0 && state >= S1_5) || (sel == 1 && state >= S2_5)) begin
                    // Dispense beverage
                    if(sel == 0) begin
                        out1 = 1;
                        total_change = state - S1_5;
                    end else begin
                        out2 = 1;
                        total_change = state - S2_5;
                    end
                    
                    if(total_change > 0) begin
                        out3 = 1;
                        if(total_change > 1) begin
                            nchange = total_change - 1;
                            nstate = S_CHANGE;
                        end else begin
                            nchange = 0;
                            nstate = S0;
                        end
                    end else begin
                        nchange = 0;
                        nstate = S0;
                    end
                end else begin
                    // Accumulate money
                    if(d1) begin
                        if(state < S3) nstate = state + 1;
                        else nstate = S3;
                    end else if(d2) begin
                        if(state < S2) nstate = state + 2;
                        else nstate = S3;
                    end else begin
                        nstate = state;
                    end
                end
            end
            S_CHANGE: begin
                out3 = 1;
                if(change > 1) begin
                    nchange = change - 1;
                    nstate = S_CHANGE;
                end else begin
                    nchange = 0;
                    nstate = S0;
                end
            end
            default: nstate = S0;
        endcase
    end
//*************code***********//
endmodule
