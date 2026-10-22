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
    reg [3:0] state, nstate;
    reg [2:0] change_cnt;
    reg d1_reg, d2_reg;
    wire d1_pulse = d1 & ~d1_reg;
    wire d2_pulse = d2 & ~d2_reg;

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            d1_reg <= 0;
            d2_reg <= 0;
        end else begin
            d1_reg <= d1;
            d2_reg <= d2;
        end
    end

    always @(*) begin
        case (state)
            S0: nstate = d1_pulse ? S0_5 : d2_pulse ? S1 : S0;
            S0_5: nstate = d1_pulse ? S1 : d2_pulse ? S1_5 : S0_5;
            S1: nstate = d1_pulse ? S1_5 : d2_pulse ? S2 : S1;
            S1_5: begin
                if (sel == 0) nstate = S0;
                else nstate = d1_pulse ? S2 : d2_pulse ? S2_5 : S1_5;
            end
            S2: begin
                if (sel == 0) nstate = S0;
                else nstate = d1_pulse ? S2_5 : d2_pulse ? S3 : S2;
            end
            S2_5: begin
                if (sel == 0) nstate = CHG;
                else nstate = S0;
            end
            S3: begin
                if (sel == 0) nstate = CHG;
                else nstate = S0;
            end
            CHG: begin
                if (change_cnt == 1) nstate = S0;
                else nstate = CHG;
            end
            default: nstate = S0;
        endcase
    end

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= S0;
            change_cnt <= 0;
        end else begin
            state <= nstate;
            case (state)
                S2_5: if (sel == 0) change_cnt <= 1;
                S3:   if (sel == 0) change_cnt <= 2;
                CHG:  change_cnt <= change_cnt - 1;
                default: change_cnt <= 0;
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
            case (state)
                S1_5: if (sel == 0) out1 <= 1;
                S2:   if (sel == 0) begin out1 <= 1; out3 <= 1; end
                S2_5: if (sel == 0) begin out1 <= 1; out3 <= 1; end
                      else out2 <= 1;
                S3:   if (sel == 0) begin out1 <= 1; out3 <= 1; end
                      else begin out2 <= 1; out3 <= 1; end
                CHG:  out3 <= 1;
                default: begin out1 <= 0; out2 <= 0; out3 <= 0; end
            endcase
        end
    end

endmodule
