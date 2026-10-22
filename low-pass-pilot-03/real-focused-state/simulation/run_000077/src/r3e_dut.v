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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, CHG=7;
    reg [2:0] state, nstate;
    reg [1:0] change_cnt, change_next;

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            change_cnt <= 0;
        end else begin
            state <= nstate;
            change_cnt <= change_next;
        end
    end

    always @(*) begin
        nstate = state;
        change_next = change_cnt;
        case(state)
            S0: nstate = d1 ? S0_5 : d2 ? S1 : S0;
            S0_5: nstate = d1 ? S1 : d2 ? S1_5 : S0_5;
            S1: nstate = d1 ? S1_5 : d2 ? S2 : S1;
            S1_5: nstate = ~sel ? S0 : d1 ? S2 : d2 ? S2_5 : S1_5;
            S2: nstate = ~sel ? S0 : d1 ? S2_5 : d2 ? S3 : S2;
            S2_5: begin
                if (~sel) begin
                    nstate = CHG;
                    change_next = 0;
                end else begin
                    nstate = S0;
                end
            end
            S3: begin
                if (~sel) begin
                    nstate = CHG;
                    change_next = 1;
                end else begin
                    nstate = S0;
                end
            end
            CHG: begin
                if (change_cnt == 0)
                    nstate = S0;
                else begin
                    nstate = CHG;
                    change_next = change_cnt - 1;
                end
            end
            default: nstate = S0;
        endcase
    end

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            {out1, out2, out3} <= 3'b000;
        end else begin
            case(state)
                S0, S0_5, S1:  {out1, out2, out3} <= 3'b000;
                S1_5:          {out1, out2, out3} <= (~sel) ? 3'b100 : 3'b000;
                S2:            {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b000;
                S2_5:          {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b010;
                S3:            {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b011;
                CHG:           {out1, out2, out3} <= 3'b001;
                default:       {out1, out2, out3} <= 3'b000;
            endcase
        end
    end

endmodule
