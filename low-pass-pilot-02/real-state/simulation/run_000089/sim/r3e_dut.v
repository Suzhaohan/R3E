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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, C0_5=7, C1=8;
    reg [3:0] state, nstate;
    
    always@(posedge clk or negedge rst) begin
        if(~rst)
            state <= S0;
        else
            state <= nstate;
    end
    
    always@(*) begin
        nstate = state;
        case(state)
            C0_5: nstate = S0;
            C1: nstate = C0_5;
            default: begin
                if (sel == 0) begin // beverage1, price 1.5
                    if (state >= S1_5) begin
                        // dispense
                        if (state == S1_5) nstate = S0;
                        else if (state == S2) nstate = S0;
                        else if (state == S2_5) nstate = C0_5;
                        else if (state == S3) nstate = C1;
                        else nstate = S0;
                    end else begin
                        // accumulate
                        if (d1) begin
                            case(state)
                                S0: nstate = S0_5;
                                S0_5: nstate = S1;
                                S1: nstate = S1_5;
                                default: nstate = state;
                            endcase
                        end else if (d2) begin
                            case(state)
                                S0: nstate = S1;
                                S0_5: nstate = S1_5;
                                S1: nstate = S2;
                                default: nstate = state;
                            endcase
                        end
                    end
                end else begin // sel == 1, beverage2, price 2.5
                    if (state >= S2_5) begin
                        // dispense
                        if (state == S2_5) nstate = S0;
                        else if (state == S3) nstate = S0;
                        else nstate = S0;
                    end else begin
                        // accumulate
                        if (d1) begin
                            case(state)
                                S0: nstate = S0_5;
                                S0_5: nstate = S1;
                                S1: nstate = S1_5;
                                S1_5: nstate = S2;
                                S2: nstate = S2_5;
                                default: nstate = state;
                            endcase
                        end else if (d2) begin
                            case(state)
                                S0: nstate = S1;
                                S0_5: nstate = S1_5;
                                S1: nstate = S2;
                                S1_5: nstate = S2_5;
                                S2: nstate = S3;
                                default: nstate = state;
                            endcase
                        end
                    end
                end
            end
        endcase
    end
    
    always@(*) begin
        out1 = 0; out2 = 0; out3 = 0;
        case(state)
            S1_5: if (~sel) out1 = 1;
            S2: if (~sel) begin out1 = 1; out3 = 1; end
            S2_5: if (~sel) begin out1 = 1; out3 = 1; end else out2 = 1;
            S3: if (~sel) begin out1 = 1; out3 = 1; end else begin out2 = 1; out3 = 1; end
            C0_5: out3 = 1;
            C1: out3 = 1;
        endcase
    end
//*************code***********//
endmodule
