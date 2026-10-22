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

    always @(posedge clk or negedge rst) begin
        if (!rst)
            state <= S0;
        else
            state <= nstate;
    end

    reg [3:0] amount;
    always @(*) begin
        case(state)
            S0: amount = 0;
            S0_5: amount = 1;
            S1: amount = 2;
            S1_5: amount = 3;
            S2: amount = 4;
            S2_5: amount = 5;
            S3: amount = 6;
            default: amount = 0;
        endcase
    end

    reg [3:0] next_amount;
    always @(*) begin
        next_amount = amount + (d1 ? 1 : 0) + (d2 ? 2 : 0);
        if (next_amount > 6) next_amount = 6;
    end

    wire dispense;
    assign dispense = (sel == 0) ? (amount >= 3) : (amount >= 5);

    always @(*) begin
        if (dispense)
            nstate = S0;
        else begin
            case(next_amount)
                0: nstate = S0;
                1: nstate = S0_5;
                2: nstate = S1;
                3: nstate = S1_5;
                4: nstate = S2;
                5: nstate = S2_5;
                6: nstate = S3;
                default: nstate = S0;
            endcase
        end
    end

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            out1 <= 0;
            out2 <= 0;
            out3 <= 0;
        end else begin
            out1 <= 0;
            out2 <= 0;
            out3 <= 0;
            case(state)
                S1_5: begin
                    if (sel == 0) out1 <= 1;
                end
                S2: begin
                    if (sel == 0) begin
                        out1 <= 1;
                        out3 <= 1;
                    end
                end
                S2_5: begin
                    if (sel == 0) begin
                        out1 <= 1;
                        out3 <= 1;
                    end else begin
                        out2 <= 1;
                    end
                end
                S3: begin
                    if (sel == 0) begin
                        out1 <= 1;
                        out3 <= 1;
                    end else begin
                        out2 <= 1;
                        out3 <= 1;
                    end
                end
            endcase
        end
    end
endmodule