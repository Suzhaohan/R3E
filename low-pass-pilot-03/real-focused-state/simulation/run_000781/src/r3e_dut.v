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
    reg d1_reg, d2_reg;

    // One-cycle input registers to match edge-detected pulse timing
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            d1_reg <= 1'b0;
            d2_reg <= 1'b0;
        end else begin
            d1_reg <= d1;
            d2_reg <= d2;
        end
    end

    // State register
    always @(posedge clk or negedge rst) begin
        if (~rst)
            state <= S0;
        else
            state <= nstate;
    end

    // Next-state logic using registered currency inputs
    always @(*) begin
        case (state)
            S0: begin
                if (d1_reg && d2_reg) nstate = S1_5;
                else if (d1_reg)      nstate = S0_5;
                else if (d2_reg)      nstate = S1;
                else                  nstate = S0;
            end
            S0_5: begin
                if (d1_reg && d2_reg) nstate = S2;
                else if (d1_reg)      nstate = S1;
                else if (d2_reg)      nstate = S1_5;
                else                  nstate = S0_5;
            end
            S1: begin
                if (d1_reg && d2_reg) nstate = S2_5;
                else if (d1_reg)      nstate = S1_5;
                else if (d2_reg)      nstate = S2;
                else                  nstate = S1;
            end
            S1_5: begin
                if (~sel) nstate = S0;
                else begin
                    if (d1_reg && d2_reg) nstate = S3;
                    else if (d1_reg)      nstate = S2;
                    else if (d2_reg)      nstate = S2_5;
                    else                  nstate = S1_5;
                end
            end
            S2: begin
                if (~sel) nstate = S0;
                else begin
                    if (d1_reg && d2_reg) nstate = S3;
                    else if (d1_reg)      nstate = S2_5;
                    else if (d2_reg)      nstate = S3;
                    else                  nstate = S2;
                end
            end
            S2_5: begin
                nstate = S0;
            end
            S3: begin
                nstate = S0;
            end
            default: nstate = S0;
        endcase
    end

    // Output logic
    always @(*) begin
        if (~rst) begin
            {out1, out2, out3} = 3'b000;
        end else begin
            case (state)
                S0, S0_5, S1: {out1, out2, out3} = 3'b000;
                S1_5        : {out1, out2, out3} = ~sel ? 3'b100 : 3'b000;
                S2          : {out1, out2, out3} = ~sel ? 3'b101 : 3'b000;
                S2_5        : {out1, out2, out3} = ~sel ? 3'b101 : 3'b010;
                S3          : {out1, out2, out3} = ~sel ? 3'b101 : 3'b011;
                default     : {out1, out2, out3} = 3'b000;
            endcase
        end
    end
//*************code***********//
endmodule
