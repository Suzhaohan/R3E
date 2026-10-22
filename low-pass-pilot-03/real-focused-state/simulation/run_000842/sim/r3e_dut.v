
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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6;
    reg[2:0] state, nstate;
    
    always@(posedge clk or negedge rst) begin
        if(~rst)
            state <= S0;
        else
            state <= nstate;
    end
    
    always@(*) begin
        case(state)
            S0     : case({d1,d2})
                        2'b10  : nstate = S0_5;
                        2'b01  : nstate = S1;
                        2'b11  : nstate = S1_5;
                        default: nstate = S0;
                     endcase
            S0_5   : case({d1,d2})
                        2'b10  : nstate = S1;
                        2'b01  : nstate = S1_5;
                        2'b11  : nstate = S2;
                        default: nstate = S0_5;
                     endcase
            S1     : case({d1,d2})
                        2'b10  : nstate = S1_5;
                        2'b01  : nstate = S2;
                        2'b11  : nstate = S2_5;
                        default: nstate = S1;
                     endcase
            S1_5   : if(~sel) nstate = S0;
                     else case({d1,d2})
                        2'b10  : nstate = S2;
                        2'b01  : nstate = S2_5;
                        2'b11  : nstate = S3;
                        default: nstate = S1_5;
                     endcase
            S2     : if(~sel) nstate = S0;
                     else case({d1,d2})
                        2'b10  : nstate = S2_5;
                        2'b01  : nstate = S3;
                        2'b11  : nstate = S3;
                        default: nstate = S2;
                     endcase
            default: nstate = S0;
        endcase
    end
    
    always@(*) begin
        if(~rst) begin
            {out1, out2, out3} = 3'b000;
        end
        else begin
            case(state)
                S0, S0_5, S1: {out1, out2, out3} = 3'b000;
                S1_5        : {out1, out2, out3} = ~sel? 3'b100: 3'b000;
                S2          : {out1, out2, out3} = ~sel? 3'b101: 3'b000;
                S2_5        : {out1, out2, out3} = ~sel? 3'b101: 3'b010;
                S3          : {out1, out2, out3} = ~sel? 3'b101: 3'b011;
                default     : {out1, out2, out3} = 3'b000;
            endcase
        end
    end
//*************code***********//
endmodule
