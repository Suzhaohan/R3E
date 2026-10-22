module TopModule(
    input wire clk,
    input wire rst,
    input wire d1,
    input wire d2,
    input wire sel,
    output reg out1,
    output reg out2,
    output reg out3
);

    localparam S0 = 3'd0,
               S0_5 = 3'd1,
               S1 = 3'd2,
               S1_5 = 3'd3,
               S2 = 3'd4,
               S2_5 = 3'd5,
               S3 = 3'd6;

    reg [2:0] state, next_state;
    reg dispensing, next_dispensing;
    reg next_out1, next_out2, next_out3;

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= S0;
            dispensing <= 0;
            out1 <= 0;
            out2 <= 0;
            out3 <= 0;
        end else begin
            state <= next_state;
            dispensing <= next_dispensing;
            out1 <= next_out1;
            out2 <= next_out2;
            out3 <= next_out3;
        end
    end

    always @(*) begin
        next_state = state;
        next_dispensing = dispensing;
        next_out1 = 0;
        next_out2 = 0;
        next_out3 = 0;

        if (dispensing) begin
            next_out3 = 1;
            case (state)
                S0_5: next_state = S0;
                S1:   next_state = S0_5;
                S1_5: next_state = S1;
                S2:   next_state = S1_5;
                S2_5: next_state = S2;
                S3:   next_state = S2_5;
                default: next_state = S0;
            endcase
            next_dispensing = (next_state != S0);
        end else begin
            if (sel == 0 && state >= S1_5) begin
                next_out1 = 1;
                case (state)
                    S1_5: begin next_out3 = 0; next_state = S0; next_dispensing = 0; end
                    S2:   begin next_out3 = 1; next_state = S0; next_dispensing = 0; end
                    S2_5: begin next_out3 = 1; next_state = S0_5; next_dispensing = 1; end
                    S3:   begin next_out3 = 1; next_state = S1; next_dispensing = 1; end
                    default: begin next_out3 = 0; next_state = S0; next_dispensing = 0; end
                endcase
            end else if (sel == 1 && state >= S2_5) begin
                next_out2 = 1;
                case (state)
                    S2_5: begin next_out3 = 0; next_state = S0; next_dispensing = 0; end
                    S3:   begin next_out3 = 1; next_state = S0; next_dispensing = 0; end
                    default: begin next_out3 = 0; next_state = S0; next_dispensing = 0; end
                endcase
            end else begin
                next_dispensing = 0;
                case (state)
                    S0: begin
                        if (d1) next_state = S0_5;
                        else if (d2) next_state = S1;
                        else next_state = S0;
                    end
                    S0_5: begin
                        if (d1) next_state = S1;
                        else if (d2) next_state = S1_5;
                        else next_state = S0_5;
                    end
                    S1: begin
                        if (d1) next_state = S1_5;
                        else if (d2) next_state = S2;
                        else next_state = S1;
                    end
                    S1_5: begin
                        if (d1) next_state = S2;
                        else if (d2) next_state = S2_5;
                        else next_state = S1_5;
                    end
                    S2: begin
                        if (d1) next_state = S2_5;
                        else if (d2) next_state = S3;
                        else next_state = S2;
                    end
                    S2_5: begin
                        if (d1) next_state = S3;
                        else if (d2) next_state = S3;
                        else next_state = S2_5;
                    end
                    S3: begin
                        next_state = S3;
                    end
                    default: next_state = S0;
                endcase
            end
        end
    end
endmodule