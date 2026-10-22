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

    parameter S0=4'd0, S0_5=4'd1, S1=4'd2, S1_5=4'd3,
              S2=4'd4, S2_5=4'd5, S3=4'd6, S3_5=4'd7, C1=4'd8;
    reg [3:0] state, nstate;
    
    always @(*) begin
        nstate = S0;
        if (state == C1) begin
            nstate = S0;
        end else begin
            if (sel == 0) begin
                // Beverage 1 price = 1.5 yuan = 3 units
                if (state >= 3) begin
                    case (state - 3)
                        0, 1: nstate = S0;
                        2:    nstate = C1;
                        default: nstate = S0;
                    endcase
                end else begin
                    case ({d1, d2})
                        2'b00: nstate = state;
                        2'b01: nstate = (state + 2 > 7) ? 7 : state + 2;
                        2'b10: nstate = (state + 1 > 7) ? 7 : state + 1;
                        2'b11: nstate = (state + 3 > 7) ? 7 : state + 3;
                    endcase
                end
            end else begin
                // Beverage 2 price = 2.5 yuan = 5 units
                if (state >= 5) begin
                    case (state - 5)
                        0, 1: nstate = S0;
                        2:    nstate = C1;
                        default: nstate = S0;
                    endcase
                end else begin
                    case ({d1, d2})
                        2'b00: nstate = state;
                        2'b01: nstate = (state + 2 > 7) ? 7 : state + 2;
                        2'b10: nstate = (state + 1 > 7) ? 7 : state + 1;
                        2'b11: nstate = (state + 3 > 7) ? 7 : state + 3;
                    endcase
                end
            end
        end
    end
    
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            out1 <= 0;
            out2 <= 0;
            out3 <= 0;
        end else begin
            state <= nstate;
            out1 <= 0;
            out2 <= 0;
            out3 <= 0;
            case (state)
                S1_5: if (sel == 0) out1 <= 1;
                S2:   if (sel == 0) begin out1 <= 1; out3 <= 1; end
                S2_5: if (sel == 0) begin out1 <= 1; out3 <= 1; end
                      else          out2 <= 1;
                S3:   if (sel == 0) begin out1 <= 1; out3 <= 1; end
                      else          begin out2 <= 1; out3 <= 1; end
                S3_5: if (sel == 0) begin out1 <= 1; out3 <= 1; end
                      else          begin out2 <= 1; out3 <= 1; end
                C1:   out3 <= 1;
                default: ;
            endcase
        end
    end

//*************code***********//
endmodule
