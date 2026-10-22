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

    localparam S0 = 4'd0, S0_5 = 4'd1, S1 = 4'd2, S1_5 = 4'd3,
               S2 = 4'd4, S2_5 = 4'd5, S3 = 4'd6, C1 = 4'd7, C2 = 4'd8;
    reg [3:0] state, nstate;
    
    always @(posedge clk or negedge rst) begin
        if (!rst)
            state <= S0;
        else
            state <= nstate;
    end
    
    always @(*) begin
        case(state)
            S0     : nstate = d1 ? S0_5 : (d2 ? S1 : S0);
            S0_5   : nstate = d1 ? S1 : (d2 ? S1_5 : S0_5);
            S1     : nstate = d1 ? S1_5 : (d2 ? S2 : S1);
            S1_5   : nstate = (~sel) ? S0 : (d1 ? S2 : (d2 ? S2_5 : S1_5));
            S2     : nstate = (~sel) ? S0 : (d1 ? S2_5 : (d2 ? S3 : S2));
            S2_5   : nstate = (~sel) ? C1 : S0;
            S3     : nstate = (~sel) ? C2 : S0;
            C1     : nstate = S0;
            C2     : nstate = C1;
            default: nstate = S0;
        endcase
    end
    
    always @(*) begin
        out1 = 1'b0;
        out2 = 1'b0;
        out3 = 1'b0;
        case(state)
            S1_5: if (~sel) out1 = 1'b1;
            S2:   if (~sel) begin out1 = 1'b1; out3 = 1'b1; end
            S2_5: if (~sel) begin out1 = 1'b1; out3 = 1'b1; end
                  else out2 = 1'b1;
            S3:   if (~sel) begin out1 = 1'b1; out3 = 1'b1; end
                  else begin out2 = 1'b1; out3 = 1'b1; end
            C1:   out3 = 1'b1;
            C2:   out3 = 1'b1;
            default: ;
        endcase
    end
//*************code***********//
endmodule
