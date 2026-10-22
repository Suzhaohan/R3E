module TopModule(
	input wire clk,
	input wire rst,
	input wire d1,
	input wire d2,
	input wire sel,
	output reg out1,
	output reg out2,
	output reg out3
);

parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, C1=7, C2=8, S3_5=9;
reg [3:0] state, nstate;

always @(posedge clk or negedge rst) begin
    if (!rst)
        state <= S0;
    else
        state <= nstate;
end

always @(*) begin
    nstate = state;
    case (state)
        S0, S0_5, S1, S1_5, S2, S2_5, S3, S3_5: begin
            if ((sel == 0 && state >= S1_5) || (sel == 1 && state >= S2_5)) begin
                case (state)
                    S1_5: nstate = S0;
                    S2:   nstate = S0;
                    S2_5: nstate = (sel == 0) ? C1 : S0;
                    S3:   nstate = (sel == 0) ? C2 : S0;
                    S3_5: nstate = (sel == 1) ? C1 : S0;
                    default: nstate = S0;
                endcase
            end else begin
                nstate = state + (d1 ? 1 : 0) + (d2 ? 2 : 0);
                if (nstate > S3_5) nstate = S3_5;
            end
        end
        C1: nstate = S0;
        C2: nstate = C1;
        default: nstate = S0;
    endcase
end

always @(*) begin
    out1 = 0;
    out2 = 0;
    out3 = 0;
    case (state)
        S0, S0_5, S1: {out1, out2, out3} = 3'b000;
        S1_5: {out1, out2, out3} = (sel == 0) ? 3'b100 : 3'b000;
        S2:   {out1, out2, out3} = (sel == 0) ? 3'b101 : 3'b000;
        S2_5: begin
            if (sel == 0) {out1, out2, out3} = 3'b101;
            else if (sel == 1) {out1, out2, out3} = 3'b010;
            else {out1, out2, out3} = 3'b000;
        end
        S3: begin
            if (sel == 0) {out1, out2, out3} = 3'b101;
            else if (sel == 1) {out1, out2, out3} = 3'b011;
            else {out1, out2, out3} = 3'b000;
        end
        S3_5: begin
            if (sel == 0) {out1, out2, out3} = 3'b101;
            else if (sel == 1) {out1, out2, out3} = 3'b011;
            else {out1, out2, out3} = 3'b000;
        end
        C1, C2: {out1, out2, out3} = 3'b001;
        default: {out1, out2, out3} = 3'b000;
    endcase
end

endmodule