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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, C1=7, C0_5=8;
    reg [3:0] state, nstate;
    reg d1_prev, d2_prev;
    wire d1_pulse = d1 & ~d1_prev;
    wire d2_pulse = d2 & ~d2_prev;

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= S0;
            d1_prev <= 1'b0;
            d2_prev <= 1'b0;
        end else begin
            state <= nstate;
            d1_prev <= d1;
            d2_prev <= d2;
        end
    end

    always @(*) begin
        nstate = state;
        case (state)
            S0: begin
                if (d1_pulse) nstate = S0_5;
                else if (d2_pulse) nstate = S1;
            end
            S0_5: begin
                if (d1_pulse) nstate = S1;
                else if (d2_pulse) nstate = S1_5;
            end
            S1: begin
                if (d1_pulse) nstate = S1_5;
                else if (d2_pulse) nstate = S2;
            end
            S1_5: begin
                if (sel) begin
                    if (d1_pulse) nstate = S2;
                    else if (d2_pulse) nstate = S2_5;
                end else begin
                    nstate = S0;
                end
            end
            S2: begin
                if (sel) begin
                    if (d1_pulse) nstate = S2_5;
                    else if (d2_pulse) nstate = S3;
                end else begin
                    nstate = S0;
                end
            end
            S2_5: begin
                if (sel) begin
                    nstate = S0;
                end else begin
                    nstate = C0_5;
                end
            end
            S3: begin
                if (sel) begin
                    nstate = S0;
                end else begin
                    nstate = C1;
                end
            end
            C1: nstate = C0_5;
            C0_5: nstate = S0;
            default: nstate = S0;
        endcase
    end

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            {out1, out2, out3} <= 3'b000;
        end else begin
            case (state)
                S0, S0_5, S1: {out1, out2, out3} <= 3'b000;
                S1_5: begin
                    if (!sel) {out1, out2, out3} <= 3'b100;
                    else {out1, out2, out3} <= 3'b000;
                end
                S2: begin
                    if (!sel) {out1, out2, out3} <= 3'b101;
                    else {out1, out2, out3} <= 3'b000;
                end
                S2_5: begin
                    if (!sel) {out1, out2, out3} <= 3'b101;
                    else {out1, out2, out3} <= 3'b010;
                end
                S3: begin
                    if (!sel) {out1, out2, out3} <= 3'b101;
                    else {out1, out2, out3} <= 3'b011;
                end
                C1: {out1, out2, out3} <= 3'b001;
                C0_5: {out1, out2, out3} <= 3'b001;
                default: {out1, out2, out3} <= 3'b000;
            endcase
        end
    end

endmodule
