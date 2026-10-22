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

    // Accumulated amount in units of 0.5 yuan
    reg [3:0] amount;

    wire [3:0] price = sel ? 5 : 3; // 2.5 yuan for sel=1, 1.5 yuan for sel=0
    wire dispense = (amount >= price);
    wire change = (amount > price);

    always @(posedge clk or negedge rst) begin
        if (!rst)
            amount <= 0;
        else if (dispense)
            amount <= 0;
        else
            amount <= amount + (d1 ? 1 : 0) + (d2 ? 2 : 0);
    end

    always @(*) begin
        if (!rst) begin
            out1 = 0;
            out2 = 0;
            out3 = 0;
        end else if (dispense) begin
            out1 = ~sel;
            out2 = sel;
            out3 = change;
        end else begin
            out1 = 0;
            out2 = 0;
            out3 = 0;
        end
    end

endmodule
