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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, S3_5=7;
    parameter CH1=8, CH2=9, CH3=10, CH4=11;

    reg [3:0] state, nstate;

    always @(posedge clk or negedge rst) begin
        if (~rst)
            state <= S0;
        else
            state <= nstate;
    end

    always @(*) begin
        nstate = state;
        case(state)
            S0: begin
                if (d1 && d2) nstate = S1_5;
                else if (d2) nstate = S1;
                else if (d1) nstate = S0_5;
                else nstate = S0;
            end
            S0_5: begin
                if (d1 && d2) nstate = S2;
                else if (d2) nstate = S1_5;
                else if (d1) nstate = S1;
                else nstate = S0_5;
            end
            S1: begin
                if (d1 && d2) nstate = S2_5;
                else if (d2) nstate = S2;
                else if (d1) nstate = S1_5;
                else nstate = S1;
            end
            S1_5: begin
                if (~sel) nstate = S0;
                else begin
                    if (d1 && d2) nstate = S3;
                    else if (d2) nstate = S2_5;
                    else if (d1) nstate = S2;
                    else nstate = S1_5;
                end
            end
            S2: begin
                if (~sel) nstate = CH1;
                else begin
                    if (d1 && d2) nstate = S3_5;
                    else if (d2) nstate = S3;
                    else if (d1) nstate = S2_5;
                    else nstate = S2;
                end
            end
            S2_5: begin
                if (~sel) nstate = CH2;
                else nstate = S0;
            end
            S3: begin
                if (~sel) nstate = CH3;
                else nstate = CH1;
            end
            S3_5: begin
                if (~sel) nstate = CH4;
                else nstate = CH2;
            end
            CH1: nstate = S0;
            CH2: nstate = CH1;
            CH3: nstate = CH2;
            CH4: nstate = CH3;
            default: nstate = S0;
        endcase
    end

    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        case(state)
            S1_5: if (~sel) out1 = 1;
            S2:   if (~sel) out1 = 1;
            S2_5: if (~sel) out1 = 1; else out2 = 1;
            S3:   if (~sel) out1 = 1; else out2 = 1;
            S3_5: if (~sel) out1 = 1; else out2 = 1;
            CH1, CH2, CH3, CH4: out3 = 1;
            default: ;
        endcase
    end

endmodule
