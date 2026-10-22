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
    localparam IDLE = 1'b0;
    localparam DISPENSE = 1'b1;

    reg state;
    reg [3:0] amount;
    reg [3:0] change;

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= IDLE;
            amount <= 0;
            change <= 0;
            out1 <= 0;
            out2 <= 0;
            out3 <= 0;
        end else begin
            case (state)
                IDLE: begin
                    if (amount >= (sel ? 5 : 3)) begin
                        if (sel) begin
                            out2 <= 1;
                            out1 <= 0;
                        end else begin
                            out1 <= 1;
                            out2 <= 0;
                        end
                        if (amount > (sel ? 5 : 3)) begin
                            out3 <= 1;
                            change <= amount - (sel ? 5 : 3) - 1;
                        end else begin
                            out3 <= 0;
                            change <= 0;
                        end
                        state <= DISPENSE;
                        amount <= 0;
                    end else begin
                        amount <= amount + (d1 ? 1 : 0) + (d2 ? 2 : 0);
                        out1 <= 0;
                        out2 <= 0;
                        out3 <= 0;
                    end
                end
                DISPENSE: begin
                    out1 <= 0;
                    out2 <= 0;
                    if (change > 0) begin
                        out3 <= 1;
                        change <= change - 1;
                    end else begin
                        out3 <= 0;
                        state <= IDLE;
                        amount <= 0;
                    end
                end
            endcase
        end
    end
endmodule
