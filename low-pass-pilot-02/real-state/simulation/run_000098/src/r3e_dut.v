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
    localparam VEND = 2'd1;
    localparam CHANGE = 2'd2;

    reg [1:0] state;
    reg [3:0] amount;
    reg [3:0] change;
    reg bev_sel;
    reg d1_r, d2_r;

    wire [3:0] price = (sel == 0) ? 4'd3 : 4'd5;

    // Combinational outputs
    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        if (state == VEND) begin
            if (bev_sel == 0) out1 = 1;
            else out2 = 1;
            if (change > 0) out3 = 1;
        end else if (state == CHANGE) begin
            out3 = 1;
        end
    end

    // Sequential logic
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= IDLE;
            amount <= 0;
            change <= 0;
            bev_sel <= 0;
            d1_r <= 0;
            d2_r <= 0;
        end else begin
            d1_r <= d1;
            d2_r <= d2;

            case (state)
                IDLE: begin
                    if (amount + (d1_r ? 4'd1 : 4'd0) + (d2_r ? 4'd2 : 4'd0) >= price) begin
                        bev_sel <= sel;
                        change <= (amount + (d1_r ? 4'd1 : 4'd0) + (d2_r ? 4'd2 : 4'd0)) - price;
                        amount <= 0;
                        state <= VEND;
                    end else begin
                        amount <= amount + (d1_r ? 4'd1 : 4'd0) + (d2_r ? 4'd2 : 4'd0);
                        state <= IDLE;
                    end
                end

                VEND: begin
                    if (change > 0) begin
                        change <= change - 1;
                        if (change - 1 > 0)
                            state <= CHANGE;
                        else
                            state <= IDLE;
                    end else begin
                        state <= IDLE;
                    end
                end

                CHANGE: begin
                    change <= change - 1;
                    if (change - 1 > 0)
                        state <= CHANGE;
                    else
                        state <= IDLE;
                end
            endcase
        end
    end

endmodule