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
    reg [1:0] change_rem;
    reg [2:0] next_state;

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= 3'd0;
            change_rem <= 2'd0;
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;
        end else begin
            if (change_rem > 0) begin
                out1 <= 1'b0;
                out2 <= 1'b0;
                out3 <= 1'b1;
                change_rem <= change_rem - 1'b1;
                state <= 3'd0;
            end else begin
                if ((sel == 1'b0 && state >= 3'd3) || (sel == 1'b1 && state >= 3'd5)) begin
                    if (sel == 1'b0) begin
                        out1 <= 1'b1;
                        out2 <= 1'b0;
                        if (state > 3'd3) begin
                            out3 <= 1'b1;
                            change_rem <= state - 3'd4;
                        end else begin
                            out3 <= 1'b0;
                            change_rem <= 2'd0;
                        end
                    end else begin
                        out1 <= 1'b0;
                        out2 <= 1'b1;
                        if (state > 3'd5) begin
                            out3 <= 1'b1;
                            change_rem <= state - 3'd6;
                        end else begin
                            out3 <= 1'b0;
                            change_rem <= 2'd0;
                        end
                    end
                    state <= 3'd0;
                end else begin
                    out1 <= 1'b0;
                    out2 <= 1'b0;
                    out3 <= 1'b0;
                    next_state = state + (d1 ? 3'd1 : 3'd0) + (d2 ? 3'd2 : 3'd0);
                    if (next_state > 3'd6)
                        state <= 3'd6;
                    else
                        state <= next_state;
                end
            end
        end
    end

endmodule
