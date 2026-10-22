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

    // Edge detection for d1 and d2
    reg d1_d, d2_d;
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            d1_d <= 1'b0;
            d2_d <= 1'b0;
        end else begin
            d1_d <= d1;
            d2_d <= d2;
        end
    end
    wire d1_pulse = d1 & ~d1_d;
    wire d2_pulse = d2 & ~d2_d;

    // State encoding
    localparam IDLE = 2'b00;
    localparam ACC  = 2'b01;
    localparam DISP = 2'b10;

    reg [1:0] state, nstate;
    reg [2:0] total; // in units of 0.5 yuan, max 6
    reg [1:0] change_cnt; // number of 0.5 coins to dispense
    reg sel_reg;
    reg give_beverage;

    // Price in units of 0.5: beverage1 = 3, beverage2 = 5
    wire [2:0] price = sel ? 3'd5 : 3'd3;
    wire [2:0] total_next = total + (d1_pulse ? 3'd1 : d2_pulse ? 3'd2 : 3'd0);

    // State and data registers
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= IDLE;
            total <= 3'd0;
            change_cnt <= 2'd0;
            sel_reg <= 1'b0;
            give_beverage <= 1'b0;
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;
        end else begin
            state <= nstate;
            // Default outputs
            out1 <= 1'b0;
            out2 <= 1'b0;
            out3 <= 1'b0;

            // Accumulate money in IDLE and ACC states
            if (state == ACC || state == IDLE) begin
                if (d1_pulse) total <= total + 1;
                else if (d2_pulse) total <= total + 2;
            end

            // Change dispensing counter
            if (state == DISP) begin
                if (change_cnt > 0) change_cnt <= change_cnt - 1;
            end

            // Detect dispense condition
            if (state == ACC && total_next >= price) begin
                sel_reg <= sel;
                change_cnt <= total_next - price;
                give_beverage <= 1'b1;
            end

            // Output logic during DISP
            if (state == DISP) begin
                if (give_beverage) begin
                    if (sel_reg == 1'b0) out1 <= 1'b1;
                    else out2 <= 1'b1;
                    give_beverage <= 1'b0;
                end
                if (change_cnt > 0) out3 <= 1'b1;
            end

            // Reset total when going back to IDLE
            if (state == DISP && change_cnt == 0) begin
                total <= 3'd0;
            end
        end
    end

    // Next state logic
    always @(*) begin
        nstate = state;
        case (state)
            IDLE: begin
                if (d1_pulse || d2_pulse) nstate = ACC;
                else nstate = IDLE;
            end
            ACC: begin
                if (total_next >= price) nstate = DISP;
                else nstate = ACC;
            end
            DISP: begin
                if (change_cnt == 0) nstate = IDLE;
                else nstate = DISP;
            end
            default: nstate = IDLE;
        endcase
    end

endmodule