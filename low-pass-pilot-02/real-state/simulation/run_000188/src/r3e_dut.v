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
    reg [1:0] add;
    
    // Next-state logic
    always @(*) begin
        // Compute amount to add based on currency inputs
        if (d1 && d2) add = 3;   // 1.5 yuan
        else if (d1)  add = 1;   // 0.5 yuan
        else if (d2)  add = 2;   // 1.0 yuan
        else          add = 0;
        
        // Default: accumulate money, capped at S3 (3.0 yuan)
        nstate = state + add;
        if (nstate > S3) nstate = S3;
        
        // Dispensing overrides based on selected beverage and current amount
        if (sel == 0) begin
            case (state)
                S1_5: nstate = S0;      // exact 1.5, dispense beverage 1
                S2:   nstate = S0;      // 2.0, dispense beverage 1 + 0.5 change
                S2_5: nstate = S2;      // 2.5, continue dispensing change
                S3:   nstate = S2_5;    // 3.0, continue dispensing change
            endcase
        end else begin
            case (state)
                S2_5: nstate = S0;      // exact 2.5, dispense beverage 2
                S3:   nstate = S0;      // 3.0, dispense beverage 2 + 0.5 change
            endcase
        end
    end
    
    // State register
    always @(posedge clk or negedge rst) begin
        if (~rst)
            state <= S0;
        else
            state <= nstate;
    end
    
    // Output logic (combinational)
    always @(*) begin
        case (state)
            S0, S0_5, S1: begin out1=0; out2=0; out3=0; end
            S1_5: begin out1 = ~sel; out2 = 0; out3 = 0; end
            S2:   begin out1 = ~sel; out2 = 0; out3 = ~sel; end
            S2_5: begin out1 = ~sel; out2 = sel; out3 = ~sel; end
            S3:   begin out1 = ~sel; out2 = sel; out3 = 1; end
            default: begin out1=0; out2=0; out3=0; end
        endcase
    end
//*************code***********//
endmodule
