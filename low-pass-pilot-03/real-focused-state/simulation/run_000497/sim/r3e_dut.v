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

    // State encoding
    parameter S0  = 4'd0;
    parameter S05 = 4'd1;
    parameter S10 = 4'd2;
    parameter S15 = 4'd3;
    parameter S20 = 4'd4;
    parameter S25 = 4'd5;
    parameter S30 = 4'd6;
    parameter C05 = 4'd7;
    parameter C10 = 4'd8;
    parameter C15 = 4'd9;

    reg [3:0] state, next_state;

    always @(posedge clk or negedge rst) begin
        if (!rst)
            state <= S0;
        else
            state <= next_state;
    end

    always @(*) begin
        next_state = state; // default
        case (state)
            S0, S05, S10, S15, S20, S25, S30: begin
                if (sel == 0 && state >= S15) begin
                    // Beverage 1 (1.5)
                    case (state)
                        S15: next_state = S0;  // change 0
                        S20: next_state = S0;  // change 0.5, out3=1 in this cycle
                        S25: next_state = C05; // change 1.0, out3=1 now, then C05 gives another
                        S30: next_state = C10; // change 1.5, out3=1 now, then C10 -> C05 -> S0
                        default: next_state = S0;
                    endcase
                end else if (sel == 1 && state >= S25) begin
                    // Beverage 2 (2.5)
                    case (state)
                        S25: next_state = S0;  // change 0
                        S30: next_state = S0;  // change 0.5, out3=1 in this cycle
                        default: next_state = S0;
                    endcase
                end else begin
                    // Accumulate
                    if (d1) begin
                        case (state)
                            S0: next_state = S05;
                            S05: next_state = S10;
                            S10: next_state = S15;
                            S15: next_state = S20;
                            S20: next_state = S25;
                            S25: next_state = S30;
                            S30: next_state = S30;
                            default: next_state = S0;
                        endcase
                    end else if (d2) begin
                        case (state)
                            S0: next_state = S10;
                            S05: next_state = S15;
                            S10: next_state = S20;
                            S15: next_state = S25;
                            S20: next_state = S30;
                            S25: next_state = S30;
                            S30: next_state = S30;
                            default: next_state = S0;
                        endcase
                    end else begin
                        next_state = state;
                    end
                end
            end
            C05: next_state = S0;
            C10: next_state = C05;
            C15: next_state = C10;
            default: next_state = S0;
        endcase
    end

    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        if (!rst) begin
            out1 = 0;
            out2 = 0;
            out3 = 0;
        end else begin
            case (state)
                S0, S05, S10: begin
                    out1 = 0; out2 = 0; out3 = 0;
                end
                S15: begin
                    if (sel == 0) begin
                        out1 = 1; out2 = 0; out3 = 0;
                    end else begin
                        out1 = 0; out2 = 0; out3 = 0;
                    end
                end
                S20: begin
                    if (sel == 0) begin
                        out1 = 1; out2 = 0; out3 = 1;
                    end else begin
                        out1 = 0; out2 = 0; out3 = 0;
                    end
                end
                S25: begin
                    if (sel == 0) begin
                        out1 = 1; out2 = 0; out3 = 1;
                    end else if (sel == 1) begin
                        out1 = 0; out2 = 1; out3 = 0;
                    end else begin
                        out1 = 0; out2 = 0; out3 = 0;
                    end
                end
                S30: begin
                    if (sel == 0) begin
                        out1 = 1; out2 = 0; out3 = 1;
                    end else if (sel == 1) begin
                        out1 = 0; out2 = 1; out3 = 1;
                    end else begin
                        out1 = 0; out2 = 0; out3 = 0;
                    end
                end
                C05: begin
                    out1 = 0; out2 = 0; out3 = 1;
                end
                C10: begin
                    out1 = 0; out2 = 0; out3 = 1;
                end
                C15: begin
                    out1 = 0; out2 = 0; out3 = 1;
                end
                default: begin
                    out1 = 0; out2 = 0; out3 = 0;
                end
            endcase
        end
    end

endmodule
