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

    // State encodes accumulated money in units of 0.5 yuan:
    // S0=0, S0_5=0.5, S1=1.0, S1_5=1.5, S2=2.0, S2_5=2.5, S3=3.0
    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6;
    reg[2:0] state, nstate;

    // d1 = 0.5 yuan (+1 unit), d2 = 1 yuan (+2 units)
    wire both = d1 & d2;   // +3 units when both inserted in the same cycle

    always@(posedge clk or negedge rst) begin
        if(~rst)
            state <= S0;
        else
            state <= nstate;
    end

    // Next-state: accumulate both currencies (incl. simultaneous), cap at S3,
    // and reset to S0 as soon as the accumulated amount covers the selected price.
    always@(*) begin
        case(state)
            S0  : nstate = both ? S1_5 : d1 ? S0_5 : d2 ? S1   : S0;
            S0_5: nstate = both ? S2   : d1 ? S1   : d2 ? S1_5 : S0_5;
            S1  : nstate = both ? S2_5 : d1 ? S1_5 : d2 ? S2   : S1;
            S1_5: nstate = ~sel ? S0 : (both ? S3 : d1 ? S2 : d2 ? S2_5 : S1_5);
            S2  : nstate = ~sel ? S0 : (both ? S3 : d1 ? S2_5 : d2 ? S3 : S2);
            S2_5: nstate = S0;
            S3  : nstate = S0;
            default: nstate = S0;
        endcase
    end

    // Moore outputs: dispense beverage when accumulated >= price; assert change
    // when accumulated strictly exceeds the selected price.
    // sel=0 -> beverage 1 (1.5), sel=1 -> beverage 2 (2.5)
    always@(*) begin
        if(~rst) begin
            {out1, out2, out3} = 3'b000;
        end
        else begin
            case(state)
                S1_5: {out1, out2, out3} = sel ? 3'b000 : 3'b100;
                S2  : {out1, out2, out3} = sel ? 3'b000 : 3'b101;
                S2_5: {out1, out2, out3} = sel ? 3'b010 : 3'b101;
                S3  : {out1, out2, out3} = sel ? 3'b011 : 3'b101;
                default: {out1, out2, out3} = 3'b000;
            endcase
        end
    end
endmodule
