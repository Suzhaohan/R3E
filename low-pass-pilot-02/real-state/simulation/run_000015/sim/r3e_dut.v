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
    reg [2:0] state;
    reg mode;
    reg first;
    reg disp_sel;
    reg [2:0] added;
    reg [2:0] total;
    reg [2:0] price;

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= 3'd0;
            mode <= 1'b0;
            first <= 1'b0;
            disp_sel <= 1'b0;
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;
        end else begin
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;

            if (mode == 1'b0) begin
                added = (d1 ? 3'd1 : 3'd0) + (d2 ? 3'd2 : 3'd0);
                price = sel ? 3'd5 : 3'd3;
                total = state + added;
                if (total >= price) begin
                    mode <= 1'b1;
                    first <= 1'b1;
                    disp_sel <= sel;
                    state <= total - price;
                end else begin
                    state <= total;
                end
            end else begin
                if (first) begin
                    if (disp_sel == 1'b0)
                        out1 <= 1'b1;
                    else
                        out2 <= 1'b1;
                    first <= 1'b0;
                end
                if (state > 3'd0) begin
                    out3 <= 1'b1;
                    state <= state - 3'd1;
                end else begin
                    mode <= 1'b0;
                end
            end
        end
    end
endmodule
