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
    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, C2=7, C1=8;
    reg [3:0] state, nstate;

    always @(posedge clk or negedge rst) begin
        if (~rst)
            state <= S0;
        else
            state <= nstate;
    end

    always @(*) begin
        case (state)
            S0: nstate = d1 ? S0_5 : d2 ? S1 : S0;
            S0_5: nstate = d1 ? S1 : d2 ? S1_5 : S0_5;
            S1: nstate = d1 ? S1_5 : d2 ? S2 : S1;
            S1_5: nstate = (sel == 0) ? S0 : (d1 ? S2 : d2 ? S2_5 : S1_5);
            S2: nstate = (sel == 0) ? S0 : (d1 ? S2_5 : d2 ? S3 : S2);
            S2_5: nstate = (sel == 0) ? C1 : S0;
            S3: nstate = (sel == 0) ? C2 : S0;
            C2: nstate = C1;
            C1: nstate = S0;
            default: nstate = S0;
        endcase
    end

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            {out1, out2, out3} <= 3'b000;
        end else begin
            out1 <= 0;
            out2 <= 0;
            out3 <= 0;
            case (state)
                S1_5: if (sel == 0) out1 <= 1;
                S2: if (sel == 0) begin out1 <= 1; out3 <= 1; end
                S2_5: if (sel == 0) begin out1 <= 1; out3 <= 1; end
                      else if (sel == 1) out2 <= 1;
                S3: if (sel == 0) begin out1 <= 1; out3 <= 1; end
                    else if (sel == 1) begin out2 <= 1; out3 <= 1; end
                C2: out3 <= 1;
                C1: out3 <= 1;
                default: ;
            endcase
        end
    end
endmodule
