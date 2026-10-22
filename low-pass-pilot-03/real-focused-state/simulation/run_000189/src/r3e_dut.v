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

    // Money states represent accumulated value in units of 0.5 yuan.
    parameter M0 = 4'd0 , M1 = 4'd1 , M2 = 4'd2 , M3 = 4'd3 ,
              M4 = 4'd4 , M5 = 4'd5 , M6 = 4'd6 ;
    // Dispense states: entering them outputs the beverage (registered).
    parameter D3 = 4'd7 , D4 = 4'd8 , D5 = 4'd9 , D6 = 4'd10 ,
              E5 = 4'd11, E6 = 4'd12;   // E* = beverage 2 dispense
    // Change states: each outputs a single 0.5-yuan coin.
    parameter C1 = 4'd13, C2 = 4'd14, C3 = 4'd15;

    reg [3:0] state, nstate;

    always @(posedge clk or negedge rst) begin
        if(!rst)
            state <= M0;
        else
            state <= nstate;
    end

    // Next-state logic.
    // For every money state the amount needed is 1.5 yuan (3 units) when
    // sel==0 and 2.5 yuan (5 units) when sel==1.  As soon as the accumulated
    // amount reaches the price we jump directly into a dispense state so that
    // the registered output appears one cycle after the triggering coin,
    // then dedicated change states hand back the overpayment 0.5 yuan at a time.
    always @(*) begin
        case(state)
            M0 : nstate = d1 ? M1 : d2 ? M2 : M0;
            M1 : nstate = d1 ? M2 : d2 ? (sel ? M3 : D3) : M1;
            M2 : nstate = d1 ? (sel ? M3 : D3)
                            : d2 ? (sel ? M4 : D4)
                            : M2;
            M3 : nstate = sel ? (d1 ? M4 : d2 ? E5 : M3) : D3;
            M4 : nstate = sel ? (d1 ? E5 : d2 ? E6 : M4) : D4;
            M5 : nstate = sel ? E5 : D5;
            M6 : nstate = sel ? E6 : D6;
            // beverage 1 dispense, then return change coins
            D3 : nstate = M0;
            D4 : nstate = C1;
            D5 : nstate = C2;
            D6 : nstate = C3;
            // beverage 2 dispense, then return change coins
            E5 : nstate = M0;
            E6 : nstate = C1;
            // change coins, one per state
            C1 : nstate = M0;
            C2 : nstate = C1;
            C3 : nstate = C2;
            default : nstate = M0;
        endcase
    end

    // Registered Moore outputs derived from the current state.
    always @(posedge clk or negedge rst) begin
        if(~rst)
            {out1, out2, out3} <= 3'b000;
        else begin
            case(state)
                D3, D4, D5, D6 : {out1, out2, out3} <= 3'b100; // beverage 1
                E5, E6         : {out1, out2, out3} <= 3'b010; // beverage 2
                C1, C2, C3     : {out1, out2, out3} <= 3'b001; // 0.5 yuan change
                default        : {out1, out2, out3} <= 3'b000;
            endcase
        end
    end
//*************code***********//
endmodule
