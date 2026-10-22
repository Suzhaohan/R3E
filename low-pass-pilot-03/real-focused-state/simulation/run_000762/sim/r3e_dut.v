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
    wire d1_pulse, d2_pulse;

    assign d1_pulse = d1 & ~d1_prev;
    assign d2_pulse = d2 & ~d2_prev;

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            d1_prev <= 1'b0;
            d2_prev <= 1'b0;
        end else begin
            state <= nstate;
            d1_prev <= d1;
            d2_prev <= d2;
        end
    end

    always @(*) begin
        case(state)
            S0:     nstate = d1_pulse ? S0_5 : d2_pulse ? S1 : S0;
            S0_5:   nstate = d1_pulse ? S1 : d2_pulse ? S1_5 : S0_5;
            S1:     nstate = d1_pulse ? S1_5 : d2_pulse ? S2 : S1;
            S1_5:   nstate = (~sel) ? S0 : (d1_pulse ? S2 : d2_pulse ? S2_5 : S1_5);
            S2:     nstate = (~sel) ? S0 : (d1_pulse ? S2_5 : d2_pulse ? S3 : S2);
            S2_5:   nstate = S0;
            S3:     nstate = S0;
            default: nstate = S0;
        endcase
    end

    always @(*) begin
        case(state)
            S0, S0_5, S1: {out1, out2, out3} = 3'b000;
            S1_5:         {out1, out2, out3} = (~sel) ? 3'b100 : 3'b000;
            S2:           {out1, out2, out3} = (~sel) ? 3'b101 : 3'b000;
            S2_5:         {out1, out2, out3} = (~sel) ? 3'b101 : 3'b010;
            S3:           {out1, out2, out3} = (~sel) ? 3'b101 : 3'b011;
            default:      {out1, out2, out3} = 3'b000;
        endcase
    end
endmodule
