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

    // State encoding (4 bits)
    parameter S0 = 0, S0_5 = 1, S1 = 2, S1_5 = 3, S2 = 4, S2_5 = 5, S3 = 6;
    parameter C0_5 = 7, C1 = 8;

    reg [3:0] state, nstate;

    // Edge detection for d1 and d2
    reg d1_r, d2_r;
    wire d1_pulse, d2_pulse;

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            d1_r <= 0;
            d2_r <= 0;
        end else begin
            d1_r <= d1;
            d2_r <= d2;
        end
    end

    assign d1_pulse = d1 & ~d1_r;
    assign d2_pulse = d2 & ~d2_r;

    // State register
    always @(posedge clk or negedge rst) begin
        if (~rst)
            state <= S0;
        else
            state <= nstate;
    end

    // Next-state logic
    always @(*) begin
        nstate = state; // default: stay
        case (state)
            S0: begin
                if (d1_pulse) nstate = S0_5;
                else if (d2_pulse) nstate = S1;
            end
            S0_5: begin
                if (d1_pulse) nstate = S1;
                else if (d2_pulse) nstate = S1_5;
            end
            S1: begin
                if (d1_pulse) nstate = S1_5;
                else if (d2_pulse) nstate = S2;
            end
            S1_5: begin
                if (~sel) nstate = S0;
                else if (d1_pulse) nstate = S2;
                else if (d2_pulse) nstate = S2_5;
            end
            S2: begin
                if (~sel) nstate = S0;
                else if (d1_pulse) nstate = S2_5;
                else if (d2_pulse) nstate = S3;
            end
            S2_5: begin
                if (~sel) nstate = C0_5;
                else nstate = S0;
            end
            S3: begin
                if (~sel) nstate = C1;
                else nstate = S0;
            end
            C0_5: nstate = S0;
            C1: nstate = C0_5;
            default: nstate = S0;
        endcase
    end

    // Output logic
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            {out1, out2, out3} <= 3'b000;
        end else begin
            case (state)
                S0, S0_5, S1: {out1, out2, out3} <= 3'b000;
                S1_5: {out1, out2, out3} <= (~sel) ? 3'b100 : 3'b000;
                S2: {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b000;
                S2_5: {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b010;
                S3: {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b011;
                C0_5: {out1, out2, out3} <= 3'b001;
                C1: {out1, out2, out3} <= 3'b001;
                default: {out1, out2, out3} <= 3'b000;
            endcase
        end
    end

endmodule
