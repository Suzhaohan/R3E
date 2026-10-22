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

    localparam S0 = 3'd0,
               S0_5 = 3'd1,
               S1 = 3'd2,
               S1_5 = 3'd3,
               S2 = 3'd4,
               S2_5 = 3'd5,
               S3 = 3'd6;

    reg [2:0] state;
    reg dispensing;

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= S0;
            dispensing <= 0;
            out1 <= 0;
            out2 <= 0;
            out3 <= 0;
        end else begin
            if (!dispensing) begin
                // Accumulation mode
                case (state)
                    S0: begin
                        if (d1) state <= S0_5;
                        else if (d2) state <= S1;
                        else state <= S0;
                        out1 <= 0; out2 <= 0; out3 <= 0;
                    end
                    S0_5: begin
                        if (d1) state <= S1;
                        else if (d2) state <= S1_5;
                        else state <= S0_5;
                        out1 <= 0; out2 <= 0; out3 <= 0;
                    end
                    S1: begin
                        if (d1) state <= S1_5;
                        else if (d2) state <= S2;
                        else state <= S1;
                        out1 <= 0; out2 <= 0; out3 <= 0;
                    end
                    S1_5: begin
                        if (sel == 0) begin
                            // Dispense beverage1, change=0
                            dispensing <= 1;
                            state <= S0;
                            out1 <= 1; out2 <= 0; out3 <= 0;
                        end else begin
                            if (d1) state <= S2;
                            else if (d2) state <= S2_5;
                            else state <= S1_5;
                            out1 <= 0; out2 <= 0; out3 <= 0;
                        end
                    end
                    S2: begin
                        if (sel == 0) begin
                            // Dispense beverage1, change=0.5
                            dispensing <= 1;
                            state <= S0_5;
                            out1 <= 1; out2 <= 0; out3 <= 1;
                        end else begin
                            if (d1) state <= S2_5;
                            else if (d2) state <= S3;
                            else state <= S2;
                            out1 <= 0; out2 <= 0; out3 <= 0;
                        end
                    end
                    S2_5: begin
                        if (sel == 0) begin
                            // Dispense beverage1, change=1.0
                            dispensing <= 1;
                            state <= S1;
                            out1 <= 1; out2 <= 0; out3 <= 1;
                        end else begin
                            // Dispense beverage2, change=0
                            dispensing <= 1;
                            state <= S0;
                            out1 <= 0; out2 <= 1; out3 <= 0;
                        end
                    end
                    S3: begin
                        if (sel == 0) begin
                            // Dispense beverage1, change=1.5
                            dispensing <= 1;
                            state <= S1_5;
                            out1 <= 1; out2 <= 0; out3 <= 1;
                        end else begin
                            // Dispense beverage2, change=0.5
                            dispensing <= 1;
                            state <= S0_5;
                            out1 <= 0; out2 <= 1; out3 <= 1;
                        end
                    end
                    default: begin
                        state <= S0;
                        out1 <= 0; out2 <= 0; out3 <= 0;
                    end
                endcase
            end else begin
                // Dispensing mode
                out1 <= 0;
                out2 <= 0;
                out3 <= (state > S0_5) ? 1 : 0;
                if (state > S0) begin
                    state <= state - 1;
                    dispensing <= (state > S0_5) ? 1 : 0;
                end else begin
                    state <= S0;
                    dispensing <= 0;
                end
            end
        end
    end

endmodule
