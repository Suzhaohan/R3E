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

    localparam ACCUM = 2'b00;
    localparam DISPENSE = 2'b01;
    localparam CHANGE = 2'b10;

    reg [1:0] state, next_state;
    reg [3:0] total, next_total;
    reg [3:0] change, next_change;

    wire [3:0] price = (sel == 0) ? 4'd3 : 4'd5;

    always @(*) begin
        next_state = state;
        next_total = total;
        next_change = change;

        case (state)
            ACCUM: begin
                if (d1)
                    next_total = total + 4'd1;
                else if (d2)
                    next_total = total + 4'd2;
                if (next_total >= price) begin
                    next_state = DISPENSE;
                    next_change = next_total - price;
                    next_total = 4'd0;
                end
            end
            DISPENSE: begin
                if (change > 0) begin
                    next_change = change - 4'd1;
                    if (next_change > 0)
                        next_state = CHANGE;
                    else
                        next_state = ACCUM;
                end else begin
                    next_state = ACCUM;
                end
            end
            CHANGE: begin
                if (change > 0) begin
                    next_change = change - 4'd1;
                    if (next_change > 0)
                        next_state = CHANGE;
                    else
                        next_state = ACCUM;
                end else begin
                    next_state = ACCUM;
                end
            end
            default: next_state = ACCUM;
        endcase
    end

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= ACCUM;
            total <= 4'd0;
            change <= 4'd0;
        end else begin
            state <= next_state;
            total <= next_total;
            change <= next_change;
        end
    end

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;
        end else begin
            case (state)
                ACCUM: begin
                    out1 <= 1'b0;
                    out2 <= 1'b0;
                    out3 <= 1'b0;
                end
                DISPENSE: begin
                    out1 <= (sel == 0) ? 1'b1 : 1'b0;
                    out2 <= (sel == 1) ? 1'b1 : 1'b0;
                    out3 <= (change > 0) ? 1'b1 : 1'b0;
                end
                CHANGE: begin
                    out1 <= 1'b0;
                    out2 <= 1'b0;
                    out3 <= 1'b1;
                end
                default: begin
                    out1 <= 1'b0;
                    out2 <= 1'b0;
                    out3 <= 1'b0;
                end
            endcase
        end
    end

endmodule