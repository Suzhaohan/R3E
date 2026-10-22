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

    localparam [2:0] S0=3'd0, S0_5=3'd1, S1=3'd2, S1_5=3'd3, S2=3'd4, S2_5=3'd5, S3=3'd6;
    reg [2:0] state, nstate;

    // Next-state logic:
    // - state holds accumulated money in 0.5-yuan units (saturate at S3 = 3.0 yuan)
    // - when the accumulated money reaches the selected beverage price,
    //   return one 0.5-yuan change coin per cycle (decrement state) until exact, then reset
    always @(*) begin
        nstate = state;
        if (sel == 1'b0 && state >= S1_5) begin           // beverage 1 costs 1.5 yuan
            if (state > S1_5)
                nstate = state - 3'd1;                    // dispense 0.5 change coin
            else
                nstate = S0;                              // exact payment, done
        end
        else if (sel == 1'b1 && state >= S2_5) begin      // beverage 2 costs 2.5 yuan
            if (state > S2_5)
                nstate = state - 3'd1;                    // dispense 0.5 change coin
            else
                nstate = S0;                              // exact payment, done
        end
        else begin
            nstate = state + (d1 ? 3'd1 : 3'd0) + (d2 ? 3'd2 : 3'd0);
            if (nstate > S3)
                nstate = S3;
        end
    end

    always @(posedge clk or negedge rst) begin
        if (!rst)
            state <= S0;
        else
            state <= nstate;
    end

    // Combinational outputs derived from current accumulated state and selection
    always @(*) begin
        out1 = 1'b0;
        out2 = 1'b0;
        out3 = 1'b0;
        if (sel == 1'b0 && state >= S1_5) begin
            out1 = 1'b1;
            if (state > S1_5)
                out3 = 1'b1;
        end
        else if (sel == 1'b1 && state >= S2_5) begin
            out2 = 1'b1;
            if (state > S2_5)
                out3 = 1'b1;
        end
    end
//*************code***********//
endmodule
