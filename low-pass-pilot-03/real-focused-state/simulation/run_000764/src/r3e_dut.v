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

    // State encoding
    localparam IDLE = 4'd0;
    localparam ACC05 = 4'd1;
    localparam ACC10 = 4'd2;
    localparam ACC15 = 4'd3;
    localparam ACC20 = 4'd4;
    localparam ACC25 = 4'd5;
    localparam ACC30 = 4'd6;
    localparam ACC35 = 4'd7;
    localparam DISP1 = 4'd8;
    localparam DISP2 = 4'd9;
    localparam CHANGE = 4'd10;

    reg [3:0] state, next_state;
    reg [2:0] chg_cnt, next_chg_cnt;
    reg [3:0] next_amt;

    // Edge detection for d1, d2
    reg d1_d, d2_d;
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            d1_d <= 0;
            d2_d <= 0;
        end else begin
            d1_d <= d1;
            d2_d <= d2;
        end
    end
    wire pulse_d1 = d1 & ~d1_d;
    wire pulse_d2 = d2 & ~d2_d;

    // State register
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= IDLE;
            chg_cnt <= 0;
        end else begin
            state <= next_state;
            chg_cnt <= next_chg_cnt;
        end
    end

    // Next-state logic
    always @(*) begin
        next_state = state;
        next_chg_cnt = chg_cnt;
        next_amt = state;

        case (state)
            IDLE, ACC05, ACC10, ACC15, ACC20, ACC25, ACC30, ACC35: begin
                // Accumulate money (d1 has priority over d2)
                if (pulse_d1) next_amt = state + 1;
                else if (pulse_d2) next_amt = state + 2;
                else next_amt = state;

                // Cap at ACC35 (3.5 yuan)
                if (next_amt > ACC35) next_amt = ACC35;

                // Check dispense conditions
                if (sel == 0) begin // Beverage 1 (1.5 yuan = 3 units)
                    if (next_amt >= ACC15) begin
                        next_state = DISP1;
                        next_chg_cnt = next_amt - ACC15;
                    end else begin
                        next_state = next_amt;
                        next_chg_cnt = 0;
                    end
                end else begin // Beverage 2 (2.5 yuan = 5 units)
                    if (next_amt >= ACC25) begin
                        next_state = DISP2;
                        next_chg_cnt = next_amt - ACC25;
                    end else begin
                        next_state = next_amt;
                        next_chg_cnt = 0;
                    end
                end
            end

            DISP1: begin
                if (chg_cnt > 0) begin
                    next_chg_cnt = chg_cnt - 1;
                    if (chg_cnt - 1 == 0) next_state = IDLE;
                    else next_state = CHANGE;
                end else begin
                    next_state = IDLE;
                    next_chg_cnt = 0;
                end
            end

            DISP2: begin
                if (chg_cnt > 0) begin
                    next_chg_cnt = chg_cnt - 1;
                    if (chg_cnt - 1 == 0) next_state = IDLE;
                    else next_state = CHANGE;
                end else begin
                    next_state = IDLE;
                    next_chg_cnt = 0;
                end
            end

            CHANGE: begin
                if (chg_cnt > 0) begin
                    next_chg_cnt = chg_cnt - 1;
                    if (chg_cnt - 1 == 0) next_state = IDLE;
                    else next_state = CHANGE;
                end else begin
                    next_state = IDLE;
                    next_chg_cnt = 0;
                end
            end

            default: begin
                next_state = IDLE;
                next_chg_cnt = 0;
            end
        endcase
    end

    // Output logic (combinational)
    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        case (state)
            DISP1: begin
                out1 = 1;
                if (chg_cnt > 0) out3 = 1;
            end
            DISP2: begin
                out2 = 1;
                if (chg_cnt > 0) out3 = 1;
            end
            CHANGE: begin
                out3 = 1;
            end
            default: begin
                out1 = 0;
                out2 = 0;
                out3 = 0;
            end
        endcase
    end

endmodule