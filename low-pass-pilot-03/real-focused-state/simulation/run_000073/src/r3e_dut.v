module TopModule(
    input wire clk  ,
    input wire rst  ,
    input wire d1 ,
    input wire d2 ,
    input wire sel ,
    
    output reg out1,
    output reg out2,
    output reg out3
);
//*************code***********//

    localparam S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, CHG=7;
    reg [2:0] state, nstate;
    reg [1:0] cnt, ncnt;
    
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            cnt <= 2'd0;
        end else begin
            state <= nstate;
            cnt <= ncnt;
        end
    end
    
    always @(*) begin
        nstate = state;
        ncnt = cnt;
        case(state)
            S0: nstate = d1 ? S0_5 : d2 ? S1 : S0;
            S0_5: nstate = d1 ? S1 : d2 ? S1_5 : S0_5;
            S1: nstate = d1 ? S1_5 : d2 ? S2 : S1;
            S1_5: begin
                if (~sel) nstate = S0;
                else nstate = d1 ? S2 : d2 ? S2_5 : S1_5;
            end
            S2: begin
                if (~sel) nstate = S0;
                else nstate = d1 ? S2_5 : d2 ? S3 : S2;
            end
            S2_5: begin
                if (~sel) begin
                    nstate = CHG;
                    ncnt = 2'd1;
                end else nstate = S0;
            end
            S3: begin
                if (~sel) begin
                    nstate = CHG;
                    ncnt = 2'd2;
                end else nstate = S0;
            end
            CHG: begin
                nstate = (cnt > 1) ? CHG : S0;
                ncnt = cnt - 1'b1;
            end
            default: nstate = S0;
        endcase
    end
    
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            {out1, out2, out3} <= 3'b000;
        end else begin
            case(state)
                S1_5: {out1, out2, out3} <= (~sel) ? 3'b100 : 3'b000;
                S2:   {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b000;
                S2_5: {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b010;
                S3:   {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b011;
                CHG:  {out1, out2, out3} <= 3'b001;
                default: {out1, out2, out3} <= 3'b000;
            endcase
        end
    end
//*************code***********//
endmodule
