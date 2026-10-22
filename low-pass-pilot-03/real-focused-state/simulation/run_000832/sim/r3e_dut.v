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

    localparam S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6;
    reg [2:0] state, nstate;

    // State register
    always @(posedge clk or negedge rst) begin
        if (~rst)
            state <= S0;
        else
            state <= nstate;
    end

    // Next-state logic (default hold, no self-reference / inferred latch)
    always @(*) begin
        nstate = state;
        case (state)
            S0   : begin
                       if (d1)      nstate = S0_5;
                       else if (d2) nstate = S1;
                   end
            S0_5 : begin
                       if (d1)      nstate = S1;
                       else if (d2) nstate = S1_5;
                   end
            S1   : begin
                       if (d1)      nstate = S1_5;
                       else if (d2) nstate = S2;
                   end
            S1_5 : begin
                       if (~sel)    nstate = S0;      // 1.5 paid, drink1 exact
                       else if (d1) nstate = S2;
                       else if (d2) nstate = S2_5;
                   end
            S2   : begin
                       if (~sel)    nstate = S0;      // 2.0 paid, drink1 + 0.5 change
                       else if (d1) nstate = S2_5;
                       else if (d2) nstate = S3;
                   end
            S2_5 : nstate = S0;                       // dispense then clear
            S3   : nstate = S0;                       // dispense then clear
            default: nstate = S0;
        endcase
    end

    // Moore output decoder: combinational from current state so the dispense
    // pulses appear on the same cycle the credit reaches the price, not one
    // clock later as with the registered decoder.
    always @(*) begin
        case (state)
            S1_5 : {out1, out2, out3} = sel ? 3'b000 : 3'b100;
            S2   : {out1, out2, out3} = sel ? 3'b000 : 3'b101;
            S2_5 : {out1, out2, out3} = sel ? 3'b010 : 3'b101;
            S3   : {out1, out2, out3} = sel ? 3'b011 : 3'b101;
            default: {out1, out2, out3} = 3'b000;
        endcase
    end
//*************code***********//
endmodule
