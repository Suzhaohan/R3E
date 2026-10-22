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

    localparam IDLE = 2'b00;
    localparam CHANGE = 2'b01;

    reg [1:0] state;
    reg [3:0] amount;
    reg [3:0] change_left;

    reg [3:0] next_amount;
    reg [3:0] next_change_left;
    reg [1:0] next_state;
    reg next_out1, next_out2, next_out3;

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= IDLE;
            amount <= 0;
            change_left <= 0;
            out1 <= 0;
            out2 <= 0;
            out3 <= 0;
        end else begin
            state <= next_state;
            amount <= next_amount;
            change_left <= next_change_left;
            out1 <= next_out1;
            out2 <= next_out2;
            out3 <= next_out3;
        end
    end

    always @(*) begin
        next_state = state;
        next_amount = amount;
        next_change_left = change_left;
        next_out1 = 0;
        next_out2 = 0;
        next_out3 = 0;

        case (state)
            IDLE: begin
                if ( (sel == 0 && amount >= 3) || (sel == 1 && amount >= 5) ) begin
                    if (sel == 0) begin
                        next_out1 = 1;
                        next_out2 = 0;
                        if (amount > 3) begin
                            next_out3 = 1;
                            next_change_left = amount - 3 - 1;
                            next_state = CHANGE;
                        end else begin
                            next_out3 = 0;
                            next_change_left = 0;
                            next_state = IDLE;
                        end
                    end else begin
                        next_out1 = 0;
                        next_out2 = 1;
                        if (amount > 5) begin
                            next_out3 = 1;
                            next_change_left = amount - 5 - 1;
                            next_state = CHANGE;
                        end else begin
                            next_out3 = 0;
                            next_change_left = 0;
                            next_state = IDLE;
                        end
                    end
                    next_amount = 0;
                end else begin
                    next_amount = amount + d1 + 2*d2;
                    next_out1 = 0;
                    next_out2 = 0;
                    next_out3 = 0;
                    next_change_left = 0;
                    next_state = IDLE;
                end
            end
            CHANGE: begin
                next_out1 = 0;
                next_out2 = 0;
                next_out3 = 1;
                if (change_left > 0) begin
                    next_change_left = change_left - 1;
                    next_state = CHANGE;
                end else begin
                    next_change_left = 0;
                    next_state = IDLE;
                end
                next_amount = amount;
            end
            default: begin
                next_state = IDLE;
                next_amount = 0;
                next_change_left = 0;
                next_out1 = 0;
                next_out2 = 0;
                next_out3 = 0;
            end
        endcase
    end

endmodule