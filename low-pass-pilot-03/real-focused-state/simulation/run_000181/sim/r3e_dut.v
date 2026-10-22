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
        
        // Dispense condition
        if (sel == 0) begin
            if (state >= S1_5) nstate = S0;
        end else begin
            if (state >= S2_5) nstate = S0;
        end
        
        // Accumulate coins if not dispensing
        if (nstate != S0) begin
            if (d1 && d2) begin
                case (state)
                    S0:   nstate = S1_5;
                    S0_5: nstate = S2;
                    S1:   nstate = S2_5;
                    S1_5: nstate = S3;
                    S2:   nstate = S3;
                    S2_5: nstate = S3;
                    S3:   nstate = S3;
                    default: nstate = S0;
                endcase
            end else if (d2) begin
                case (state)
                    S0:   nstate = S1;
                    S0_5: nstate = S1_5;
                    S1:   nstate = S2;
                    S1_5: nstate = S2_5;
                    S2:   nstate = S3;
                    S2_5: nstate = S3;
                    S3:   nstate = S3;
                    default: nstate = S0;
                endcase
            end else if (d1) begin
                case (state)
                    S0:   nstate = S0_5;
                    S0_5: nstate = S1;
                    S1:   nstate = S1_5;
                    S1_5: nstate = S2;
                    S2:   nstate = S2_5;
                    S2_5: nstate = S3;
                    S3:   nstate = S3;
                    default: nstate = S0;
                endcase
            end
        end
    end
    
    always @(*) begin
        case (state)
            S0, S0_5, S1:  {out1, out2, out3} = 3'b000;
            S1_5:          {out1, out2, out3} = (~sel) ? 3'b100 : 3'b000;
            S2:            {out1, out2, out3} = (~sel) ? 3'b101 : 3'b000;
            S2_5:          {out1, out2, out3} = (~sel) ? 3'b101 : 3'b010;
            S3:            {out1, out2, out3} = (~sel) ? 3'b101 : 3'b011;
            default:        {out1, out2, out3} = 3'b000;
        endcase
    end
//*************code***********//
endmodule
