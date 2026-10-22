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

    reg [3:0] total;
    reg [3:0] change;

    wire [3:0] price = sel ? 5 : 3; // 2.5 or 1.5 yuan in 0.5 units

    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        if (change > 0) begin
            out3 = 1;
        end else if (total >= price) begin
            if (sel == 0)
                out1 = 1;
            else
                out2 = 1;
        end
    end

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            total <= 0;
            change <= 0;
        end else begin
            if (change > 0) begin
                change <= change - 1;
            end else if (total >= price) begin
                change <= total - price;
                total <= 0;
            end else begin
                if (d1 && d2)
                    total <= total + 3;
                else if (d1)
                    total <= total + 1;
                else if (d2)
                    total <= total + 2;
            end
        end
    end

endmodule
