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

    localparam S0 = 4'd0,
               S0_5 = 4'd1,
               S1 = 4'd2,
               S1_5 = 4'd3,
               S2 = 4'd4,
               S2_5 = 4'd5,
               S3 = 4'd6,
               CHG = 4'd7;

    reg [3:0] state, nstate;
    reg [2:0] change_cnt, nchange_cnt;

    reg d1_prev, d2_prev;
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            d1_prev <= 1'b0;
            d2_prev <= 1'b0;
        end else begin
            d1_prev <= d1;
            d2_prev <= d2;
        end
    end

    wire d1_pulse = d1 & ~d1_prev;
    wire d2_pulse = d2 & ~d2_prev;

    reg [2:0] amount;
    always @(*) begin
        case(state)
            S0: amount = 3'd0;
            S0_5: amount = 3'd1;
            S1: amount = 3'd2;
            S1_5: amount = 3'd3;
            S2: amount = 3'd4;
            S2_5: amount = 3'd5;
            S3: amount = 3'd6;
            default: amount = 3'd0;
        endcase
    end

    wire [2:0] price = sel ? 3'd5 : 3'd3;

    always @(*) begin
        nstate = state;
        nchange_cnt = change_cnt;
        case(state)
            S0, S0_5, S1, S1_5, S2, S2_5, S3: begin
                if (amount >= price) begin
                    if (amount > price + 1) begin
                        nstate = CHG;
                        nchange_cnt = amount - price - 1;
                    end else begin
                        nstate = S0;
                        nchange_cnt = 3'd0;
                    end
                end else begin
                    if (d1_pulse) begin
                        case(state)
                            S0: nstate = S0_5;
                            S0_5: nstate = S1;
                            S1: nstate = S1_5;
                            S1_5: nstate = S2;
                            S2: nstate = S2_5;
                            S2_5: nstate = S3;
                            S3: nstate = S3;
                            default: nstate = state;
                        endcase
                    end else if (d2_pulse) begin
                        case(state)
                            S0: nstate = S1;
                            S0_5: nstate = S1_5;
                            S1: nstate = S2;
                            S1_5: nstate = S2_5;
                            S2: nstate = S3;
                            S2_5: nstate = S3;
                            S3: nstate = S3;
                            default: nstate = state;
                        endcase
                    end else begin
                        nstate = state;
                    end
                end
            end
            CHG: begin
                if (change_cnt > 1) begin
                    nstate = CHG;
                    nchange_cnt = change_cnt - 1;
                end else begin
                    nstate = S0;
                    nchange_cnt = 3'd0;
                end
            end
            default: nstate = S0;
        endcase
    end

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            change_cnt <= 3'd0;
        end else begin
            state <= nstate;
            change_cnt <= nchange_cnt;
        end
    end

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;
        end else begin
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;
            case(state)
                S0, S0_5, S1, S1_5, S2, S2_5, S3: begin
                    if (amount >= price) begin
                        if (sel) out2 <= 1'b1;
                        else out1 <= 1'b1;
                        if (amount > price) out3 <= 1'b1;
                    end
                end
                CHG: begin
                    out3 <= 1'b1;
                end
                default: begin end
            endcase
        end
    end

endmodule
