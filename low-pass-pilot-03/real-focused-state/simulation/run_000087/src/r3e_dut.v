
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
        nstate = state;
        case(state)
            S0: begin
                if(d2) nstate = S1;
                else if(d1) nstate = S0_5;
            end
            S0_5: begin
                if(d2) nstate = S1_5;
                else if(d1) nstate = S1;
            end
            S1: begin
                if(d2) nstate = S2;
                else if(d1) nstate = S1_5;
            end
            S1_5: begin
                if(~sel) nstate = S0;
                else if(d2) nstate = S2_5;
                else if(d1) nstate = S2;
            end
            S2: begin
                if(~sel) nstate = S0;
                else if(d2) nstate = S3;
                else if(d1) nstate = S2_5;
            end
            S2_5: nstate = S0;
            S3: nstate = S0;
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
