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
    reg [2:0] state, nstate;

    always @(posedge clk or negedge rst) begin
        if(!rst) state <= S0;
        else     state <= nstate;
    end

    // Accumulator / dispense FSM.  Money states:
    //   S0=0.0  S0_5=0.5  S1=1.0  S1_5=1.5  S2=2.0  S2_5=2.5  S3=3.0
    // sel=0 chooses beverage 1 (1.5), sel=1 chooses beverage 2 (2.5).
    // A coin is added on the first matching input (d1 first, then d2),
    // reproducing the level-based priority behaviour seen in the trace.
    always @(*) begin
        nstate = state;            // explicit hold
        case(state)
            S0   : if(d1)      nstate = S0_5;
                   else if(d2) nstate = S1;
            S0_5 : if(d1)      nstate = S1;     // 0.5+0.5
                   else if(d2) nstate = S1_5;   // 0.5+1.0  (was S1)
            S1   : if(d1)      nstate = S1_5;   // 1.0+0.5
                   else if(d2) nstate = S2;     // 1.0+1.0
            S1_5 : if(~sel)    nstate = S0;     // dispense beverage1 (exact)
                   else if(d1) nstate = S2;     // 1.5+0.5
                   else if(d2) nstate = S2_5;   // 1.5+1.0 (was S2)
            S2   : if(~sel)    nstate = S0;     // dispense beverage1 + change
                   else if(d1) nstate = S2_5;   // 2.0+0.5
                   else if(d2) nstate = S3;     // 2.0+1.0
            S2_5 : nstate = S0;                 // dispense beverage2 (or beverage1+change)
            S3   : nstate = S0;                 // dispense beverage1/2 + change
            default: nstate = S0;
        endcase
    end

    always @(*) begin
        {out1, out2, out3} = 3'b000;
        case(state)
            S1_5 : if(~sel) {out1, out2, out3} = 3'b100;                        // bev1
            S2   : if(~sel) {out1, out2, out3} = 3'b101;                        // bev1 + 0.5 change
            S2_5 : if(~sel) {out1, out2, out3} = 3'b101;                        // bev1 + change
                   else     {out1, out2, out3} = 3'b010;                        // bev2
            S3   : if(~sel) {out1, out2, out3} = 3'b101;                        // bev1 + change
                   else     {out1, out2, out3} = 3'b011;                        // bev2 + 0.5 change
            default: {out1, out2, out3} = 3'b000;
        endcase
    end
//*************code***********//
endmodule
