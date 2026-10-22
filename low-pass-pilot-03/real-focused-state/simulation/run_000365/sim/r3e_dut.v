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
    reg [3:0] amount;
    reg [3:0] change;
    reg [1:0] state;
    localparam IDLE = 2'd0, DISPENSE = 2'd1, CHANGE = 2'd2;

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            amount <= 4'd0;
            change <= 4'd0;
            state <= IDLE;
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;
        end else begin
            case (state)
                IDLE: begin
                    out1 <= 1'b0;
                    out2 <= 1'b0;
                    out3 <= 1'b0;
                    if (d1) amount <= amount + 4'd1;
                    else if (d2) amount <= amount + 4'd2;
                    if (sel == 1'b0 && amount >= 4'd3) begin
                        state <= DISPENSE;
                        change <= amount - 4'd3;
                        out1 <= 1'b1;
                        out2 <= 1'b0;
                        if (amount - 4'd3 > 0) begin
                            out3 <= 1'b1;
                            change <= amount - 4'd4;
                        end else begin
                            out3 <= 1'b0;
                            change <= 4'd0;
                        end
                        amount <= 4'd0;
                    end else if (sel == 1'b1 && amount >= 4'd5) begin
                        state <= DISPENSE;
                        change <= amount - 4'd5;
                        out1 <= 1'b0;
                        out2 <= 1'b1;
                        if (amount - 4'd5 > 0) begin
                            out3 <= 1'b1;
                            change <= amount - 4'd6;
                        end else begin
                            out3 <= 1'b0;
                            change <= 4'd0;
                        end
                        amount <= 4'd0;
                    end
                end
                DISPENSE: begin
                    out1 <= 1'b0;
                    out2 <= 1'b0;
                    if (change > 0) begin
                        out3 <= 1'b1;
                        change <= change - 4'd1;
                        state <= DISPENSE;
                    end else begin
                        out3 <= 1'b0;
                        state <= IDLE;
                    end
                end
                CHANGE: begin
                    out1 <= 1'b0;
                    out2 <= 1'b0;
                    out3 <= 1'b0;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
