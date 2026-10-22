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

    // State encoding: amount in units of 0.5 yuan
    parameter S0 = 3'd0,
              S0_5 = 3'd1,
              S1 = 3'd2,
              S1_5 = 3'd3,
              S2 = 3'd4,
              S2_5 = 3'd5,
              S3 = 3'd6;

    reg [2:0] state, nstate;
    reg mode, nmode;

    // Next state logic
    always @(*) begin
        // Default
        nstate = state;
        nmode = mode;

        if (mode == 0) begin
            // Accumulate mode
            if (d1 && d2) begin
                if (state + 3 > 6) nstate = 6;
                else nstate = state + 3;
            end else if (d2) begin
                if (state + 2 > 6) nstate = 6;
                else nstate = state + 2;
            end else if (d1) begin
                if (state + 1 > 6) nstate = 6;
                else nstate = state + 1;
            end else begin
                nstate = state;
            end

            // Check dispense
            if (sel == 0 && state >= S1_5) begin
                // Dispense beverage 1
                if (state > S1_5) begin
                    nstate = state - S1_5 - 1;
                    nmode = (nstate > 0) ? 1 : 0;
                end else begin
                    nstate = 0;
                    nmode = 0;
                end
            end else if (sel == 1 && state >= S2_5) begin
                // Dispense beverage 2
                if (state > S2_5) begin
                    nstate = state - S2_5 - 1;
                    nmode = (nstate > 0) ? 1 : 0;
                end else begin
                    nstate = 0;
                    nmode = 0;
                end
            end
        end else begin
            // mode == 1: dispensing change
            if (state > 0) begin
                nstate = state - 1;
                nmode = (nstate > 0) ? 1 : 0;
            end else begin
                nstate = 0;
                nmode = 0;
            end
        end
    end

    // State and mode registers
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= 0;
            mode <= 0;
        end else begin
            state <= nstate;
            mode <= nmode;
        end
    end

    // Output logic (combinational)
    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;

        if (mode == 0) begin
            if (sel == 0 && state >= S1_5) begin
                out1 = 1;
                if (state > S1_5) out3 = 1;
            end else if (sel == 1 && state >= S2_5) begin
                out2 = 1;
                if (state > S2_5) out3 = 1;
            end
        end else begin
            // mode == 1
            if (state > 0) out3 = 1;
        end
    end

endmodule
