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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, CH1=7, CH2=8;
    reg[3:0] state, nstate;
    
    always@(posedge clk or negedge rst) begin
        if(~rst)
            state <= S0;
        else
            state <= nstate;
    end
    
    always@(*) begin
        case(state)
            S0     : nstate = d1 ? (d2 ? S1_5 : S0_5) : (d2 ? S1 : S0);
            S0_5   : nstate = d1 ? (d2 ? S2 : S1) : (d2 ? S1_5 : S0_5);
            S1     : nstate = d1 ? (d2 ? S2_5 : S1_5) : (d2 ? S2 : S1);
            S1_5   : if (sel==0) nstate = S0;
                     else nstate = d1 ? (d2 ? S3 : S2) : (d2 ? S2_5 : S1_5);
            S2     : if (sel==0) nstate = S0;
                     else nstate = d1 ? (d2 ? S3 : S2_5) : (d2 ? S3 : S2);
            S2_5   : if (sel==0) nstate = CH1;
                     else nstate = S0;
            S3     : if (sel==0) nstate = CH2;
                     else nstate = S0;
            CH1    : nstate = S0;
            CH2    : nstate = CH1;
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
                S1_5        : {out1, out2, out3} = (sel==0) ? 3'b100 : 3'b000;
                S2          : {out1, out2, out3} = (sel==0) ? 3'b101 : 3'b000;
                S2_5        : {out1, out2, out3} = (sel==0) ? 3'b101 : (sel==1) ? 3'b010 : 3'b000;
                S3          : {out1, out2, out3} = (sel==0) ? 3'b101 : (sel==1) ? 3'b011 : 3'b000;
                CH1         : {out1, out2, out3} = 3'b001;
                CH2         : {out1, out2, out3} = 3'b001;
                default     : {out1, out2, out3} = 3'b000;
            endcase
        end
    end
//*************code***********//
endmodule
