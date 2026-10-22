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
    
    // Next-state logic: default to holding the current state, then
    // accumulate currency (0.5 for d1, 1.0 for d2). When the selected
    // beverage is affordable, dispense and return to S0.
    always@(*) begin
        nstate = state;
        case(state)
            S0     : if(d1)      nstate = S0_5;
                     else if(d2) nstate = S1;
            S0_5   : if(d1)      nstate = S1;
                     else if(d2) nstate = S1_5;
            S1     : if(d1)      nstate = S1_5;
                     else if(d2) nstate = S2;
            S1_5   : if(~sel)    nstate = S0;
                     else if(d1) nstate = S2;
                     else if(d2) nstate = S2_5;
            S2     : if(~sel)    nstate = S0;
                     else if(d1) nstate = S2_5;
                     else if(d2) nstate = S3;
            S2_5   : nstate = S0;
            S3     : nstate = S0;
            default: nstate = S0;
        endcase
    end
    
    // Output logic is COMBINATIONAL on the current state so that the
    // dispense pulse appears in the same cycle as the state that owns it.
    always@(*) begin
        case(state)
            S1_5 : {out1, out2, out3} = (~sel) ? 3'b100 : 3'b000;
            S2   : {out1, out2, out3} = (~sel) ? 3'b101 : 3'b000;
            S2_5 : {out1, out2, out3} = (~sel) ? 3'b101 : 3'b010;
            S3   : {out1, out2, out3} = (~sel) ? 3'b101 : 3'b011;
            default: {out1, out2, out3} = 3'b000;
        endcase
    end
//*************code***********//
endmodule
