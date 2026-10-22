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

    localparam IDLE = 2'd0;
    localparam DISPENSE = 2'd1;
    localparam CHANGE = 2'd2;

    reg [1:0] state;
    reg [3:0] money;
    reg [3:0] total;
    reg [3:0] change;

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= IDLE;
            money <= 4'd0;
            total <= 4'd0;
            change <= 4'd0;
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;
        end else begin
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;

            case (state)
                IDLE: begin
                    if (money + (d1 ? 4'd1 : 4'd0) + (d2 ? 4'd2 : 4'd0) >= (sel ? 4'd5 : 4'd3)) begin
                        state <= DISPENSE;
                        total <= money + (d1 ? 4'd1 : 4'd0) + (d2 ? 4'd2 : 4'd0);
                        money <= 4'd0;
                    end else begin
                        money <= money + (d1 ? 4'd1 : 4'd0) + (d2 ? 4'd2 : 4'd0);
                        state <= IDLE;
                    end
                end

                DISPENSE: begin
                    if (sel == 1'b0) out1 <= 1'b1;
                    else out2 <= 1'b1;

                    if (total > (sel ? 4'd5 : 4'd3)) begin
                        out3 <= 1'b1;
                        change <= total - (sel ? 4'd5 : 4'd3) - 4'd1;
                        if (total - (sel ? 4'd5 : 4'd3) - 4'd1 > 4'd0)
                            state <= CHANGE;
                        else
                            state <= IDLE;
                    end else begin
                        change <= 4'd0;
                        state <= IDLE;
                    end
                end

                CHANGE: begin
                    out3 <= 1'b1;
                    if (change > 4'd1) begin
                        change <= change - 4'd1;
                        state <= CHANGE;
                    end else begin
                        change <= 4'd0;
                        state <= IDLE;
                    end
                end
            endcase
        end
    end

endmodule