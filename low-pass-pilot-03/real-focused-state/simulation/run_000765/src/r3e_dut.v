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

    reg [3:0] state;
    reg [3:0] change;
    reg d1_r, d2_r;

    wire d1_pulse = d1 & ~d1_r;
    wire d2_pulse = d2 & ~d2_r;
    wire [3:0] price = sel ? 4'd5 : 4'd3;

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= 4'd0;
            change <= 4'd0;
            d1_r <= 1'b0;
            d2_r <= 1'b0;
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;
        end else begin
            d1_r <= d1;
            d2_r <= d2;

            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;

            if (change > 0) begin
                out3 <= 1'b1;
                change <= change - 1'b1;
            end else if (state >= price) begin
                if (sel)
                    out2 <= 1'b1;
                else
                    out1 <= 1'b1;

                if (state > price) begin
                    out3 <= 1'b1;
                    change <= state - price - 1'b1;
                end else begin
                    change <= 4'd0;
                end
                state <= 4'd0;
            end else begin
                if (d1_pulse)
                    state <= state + 1'b1;
                else if (d2_pulse)
                    state <= state + 2'd2;
            end
        end
    end
endmodule
