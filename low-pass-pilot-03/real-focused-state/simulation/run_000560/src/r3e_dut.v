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
    localparam IDLE = 2'b00;
    localparam DISPENSE = 2'b01;
    localparam CHANGE = 2'b10;

    reg [1:0] state, next_state;
    reg [3:0] credit; // in 0.5 units
    reg [3:0] change; // in 0.5 units
    reg beverage; // 0 for out1, 1 for out2

    wire [3:0] price = (sel == 0) ? 4'd3 : 4'd5; // 1.5 -> 3, 2.5 -> 5
    wire [3:0] add = d1 ? 4'd1 : (d2 ? 4'd2 : 4'd0);

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= IDLE;
            credit <= 0;
            change <= 0;
            beverage <= 0;
            out1 <= 0;
            out2 <= 0;
            out3 <= 0;
        end else begin
            state <= next_state;
            case (state)
                IDLE: begin
                    out1 <= 0;
                    out2 <= 0;
                    out3 <= 0;
                    if (credit + add >= price) begin
                        change <= credit + add - price;
                        beverage <= sel;
                        credit <= 0;
                        next_state <= DISPENSE;
                    end else begin
                        credit <= credit + add;
                        next_state <= IDLE;
                    end
                end
                DISPENSE: begin
                    out1 <= (beverage == 0);
                    out2 <= (beverage == 1);
                    out3 <= (change > 0);
                    if (change > 0) begin
                        change <= change - 1;
                        next_state <= CHANGE;
                    end else begin
                        next_state <= IDLE;
                    end
                end
                CHANGE: begin
                    out1 <= 0;
                    out2 <= 0;
                    out3 <= 1;
                    if (change > 1) begin
                        change <= change - 1;
                        next_state <= CHANGE;
                    end else begin
                        change <= 0;
                        next_state <= IDLE;
                    end
                end
                default: next_state <= IDLE;
            endcase
        end
    end

endmodule
