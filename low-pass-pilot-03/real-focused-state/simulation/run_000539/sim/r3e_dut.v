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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6;
    reg [2:0] state, nstate;
    reg d1_prev, d2_prev;
    reg coin1, coin2;

    // Registered edge detection for d1 and d2
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            d1_prev <= 1'b0;
            d2_prev <= 1'b0;
            coin1 <= 1'b0;
            coin2 <= 1'b0;
        end else begin
            d1_prev <= d1;
            d2_prev <= d2;
            coin1 <= d1 & ~d1_prev;
            coin2 <= d2 & ~d2_prev;
        end
    end

    // State register
    always @(posedge clk or negedge rst) begin
        if (!rst)
            state <= S0;
        else
            state <= nstate;
    end

    // Next-state logic: dispense if enough for selected beverage, else accumulate
    reg [3:0] money;
    always @(*) begin
        if ( (sel == 1'b0 && state >= S1_5) || (sel == 1'b1 && state >= S2_5) ) begin
            nstate = S0;
        end else begin
            money = {1'b0, state};
            if (coin1) money = money + 1'b1;
            if (coin2) money = money + 2'd2;
            if (money > 6)
                nstate = S3;
            else
                nstate = money[2:0];
        end
    end

    // Output logic (unchanged from original)
    always @(*) begin
        if (!rst) begin
            {out1, out2, out3} = 3'b000;
        end else begin
            case (state)
                S0, S0_5, S1: {out1, out2, out3} = 3'b000;
                S1_5        : {out1, out2, out3} = (~sel) ? 3'b100 : 3'b000;
                S2          : {out1, out2, out3} = (~sel) ? 3'b101 : 3'b000;
                S2_5        : {out1, out2, out3} = (~sel) ? 3'b101 : 3'b010;
                S3          : {out1, out2, out3} = (~sel) ? 3'b101 : 3'b011;
                default     : {out1, out2, out3} = 3'b000;
            endcase
        end
    end
endmodule