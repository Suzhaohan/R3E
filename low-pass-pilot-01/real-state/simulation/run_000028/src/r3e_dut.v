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

	parameter S0=4'd0, S1=4'd1, S2=4'd2, S3=4'd3, S4=4'd4, S5=4'd5, S6=4'd6, C1=4'd7, C2=4'd8;
	reg [3:0] state, nstate;

	always @(posedge clk or negedge rst) begin
		if (!rst)
			state <= S0;
		else
			state <= nstate;
	end

	always @(*) begin
		case(state)
			S0,S1,S2,S3,S4,S5,S6: begin
				if ( (sel == 0 && state >= S3) || (sel == 1 && state >= S5) ) begin
					if (sel == 0) begin
						case(state)
							S3: nstate = S0;
							S4: nstate = S0;
							S5: nstate = C1;
							S6: nstate = C2;
							default: nstate = S0;
						endcase
					end else begin
						case(state)
							S5: nstate = S0;
							S6: nstate = S0;
							default: nstate = S0;
						endcase
					end
				end else begin
					if (d1 && d2) nstate = (state + 3 > S6) ? S6 : state + 3;
					else if (d1) nstate = (state + 1 > S6) ? S6 : state + 1;
					else if (d2) nstate = (state + 2 > S6) ? S6 : state + 2;
					else nstate = state;
				end
			end
			C1: nstate = S0;
			C2: nstate = C1;
			default: nstate = S0;
		endcase
	end

	always @(posedge clk or negedge rst) begin
		if (!rst) begin
			out1 <= 0;
			out2 <= 0;
			out3 <= 0;
		end else begin
			case(state)
				S0,S1,S2: {out1,out2,out3} <= 3'b000;
				S3: {out1,out2,out3} <= ~sel ? 3'b100 : 3'b000;
				S4: {out1,out2,out3} <= ~sel ? 3'b101 : 3'b000;
				S5: {out1,out2,out3} <= ~sel ? 3'b101 : 3'b010;
				S6: {out1,out2,out3} <= ~sel ? 3'b101 : 3'b011;
				C1,C2: {out1,out2,out3} <= 3'b001;
				default: {out1,out2,out3} <= 3'b000;
			endcase
		end
	end

endmodule