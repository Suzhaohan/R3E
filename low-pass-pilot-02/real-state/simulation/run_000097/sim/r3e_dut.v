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

    parameter S0 = 4'd0,
              S0_5 = 4'd1,
              S1 = 4'd2,
              S1_5 = 4'd3,
              S2 = 4'd4,
              S2_5 = 4'd5,
              S3 = 4'd6,
              CH0_5 = 4'd7,
              CH1_0 = 4'd8;

    reg [3:0] state, next;

    always @(posedge clk or negedge rst) begin
        if (!rst)
            state <= S0;
        else
            state <= next;
    end

    function [3:0] add_money;
        input [3:0] st;
        input [1:0] add;
        begin
            case (st)
                S0: begin
                    if (add == 1) add_money = S0_5;
                    else if (add == 2) add_money = S1;
                    else if (add == 3) add_money = S1_5;
                    else add_money = S0;
                end
                S0_5: begin
                    if (add == 1) add_money = S1;
                    else if (add == 2) add_money = S1_5;
                    else if (add == 3) add_money = S2;
                    else add_money = S0_5;
                end
                S1: begin
                    if (add == 1) add_money = S1_5;
                    else if (add == 2) add_money = S2;
                    else if (add == 3) add_money = S2_5;
                    else add_money = S1;
                end
                S1_5: begin
                    if (add == 1) add_money = S2;
                    else if (add == 2) add_money = S2_5;
                    else if (add == 3) add_money = S3;
                    else add_money = S1_5;
                end
                S2: begin
                    if (add == 1) add_money = S2_5;
                    else if (add == 2) add_money = S3;
                    else if (add == 3) add_money = S3;
                    else add_money = S2;
                end
                S2_5: begin
                    if (add == 1) add_money = S3;
                    else if (add == 2) add_money = S3;
                    else if (add == 3) add_money = S3;
                    else add_money = S2_5;
                end
                S3: add_money = S3;
                default: add_money = S0;
            endcase
        end
    endfunction

    always @(*) begin
        next = state;
        case (state)
            S0, S0_5, S1, S1_5, S2, S2_5, S3: begin
                if (sel == 0) begin
                    case (state)
                        S1_5: next = S0;
                        S2:   next = S0;
                        S2_5: next = CH0_5;
                        S3:   next = CH1_0;
                        default: begin
                            if (d1 && d2) next = add_money(state, 3);
                            else if (d1) next = add_money(state, 1);
                            else if (d2) next = add_money(state, 2);
                            else next = state;
                        end
                    endcase
                end else begin
                    case (state)
                        S2_5: next = S0;
                        S3:   next = S0;
                        default: begin
                            if (d1 && d2) next = add_money(state, 3);
                            else if (d1) next = add_money(state, 1);
                            else if (d2) next = add_money(state, 2);
                            else next = state;
                        end
                    endcase
                end
            end
            CH0_5: next = S0;
            CH1_0: next = CH0_5;
            default: next = S0;
        endcase
    end

    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        case (state)
            S1_5: if (sel == 0) out1 = 1;
            S2:   if (sel == 0) begin out1 = 1; out3 = 1; end
            S2_5: if (sel == 0) begin out1 = 1; out3 = 1; end
                  else if (sel == 1) out2 = 1;
            S3:   if (sel == 0) begin out1 = 1; out3 = 1; end
                  else if (sel == 1) begin out2 = 1; out3 = 1; end
            CH0_5: out3 = 1;
            CH1_0: out3 = 1;
            default: begin out1 = 0; out2 = 0; out3 = 0; end
        endcase
    end

endmodule