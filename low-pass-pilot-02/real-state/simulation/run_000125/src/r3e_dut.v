
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
//*************code***********//

	// Sx   : accumulated money worth x*0.5 yuan (0 .. 3.5)
	// CHx  : "still owe x*0.5 yuan of change" dispensing states
	localparam S0   = 4'd0,
	           S0_5 = 4'd1,
	           S1   = 4'd2,
	           S1_5 = 4'd3,
	           S2   = 4'd4,
	           S2_5 = 4'd5,
	           S3   = 4'd6,
	           S3_5 = 4'd7,
	           CH0_5= 4'd8,
	           CH1_0= 4'd9,
	           CH1_5= 4'd10;

	reg [3:0] state, nstate;

	always@(posedge clk or negedge rst) begin
		if(~rst)
			state <= S0;
		else
			state <= nstate;
	end

	// Next state: accumulate money while below the selected price,
	// dispense (and return change) once the price is reached.
	// d1 adds 0.5, d2 adds 1.0, both add 1.5. Inputs are ignored on
	// dispense cycles so that a coin seen while dispensing is dropped.
	always@(*) begin
		nstate = state;
		case(state)
			S0: begin
				if(d1 && d2)  nstate = S1_5;
				else if(d1)   nstate = S0_5;
				else if(d2)   nstate = S1;
			end
			S0_5: begin
				if(d1 && d2)  nstate = S2;
				else if(d1)   nstate = S1;
				else if(d2)   nstate = S1_5;
			end
			S1: begin
				if(d1 && d2)  nstate = S2_5;
				else if(d1)   nstate = S1_5;
				else if(d2)   nstate = S2;
			end
			S1_5: begin
				if(!sel)      nstate = S0;            // 1.5 yuan, beverage1
				else begin
					if(d1 && d2) nstate = S3;
					else if(d1)  nstate = S2;
					else if(d2)  nstate = S2_5;
				end
			end
			S2: begin
				if(!sel)      nstate = S0;            // beverage1 + 0.5 change
				else begin
					if(d1 && d2) nstate = S3_5;
					else if(d1)  nstate = S2_5;
					else if(d2)  nstate = S3;
				end
			end
			S2_5: nstate = sel ? S0   : CH0_5;   // bev2 exact / bev1 + 1.0 change
			S3:   nstate = sel ? S0   : CH1_0;   // bev2 + 0.5 / bev1 + 1.5 change
			S3_5: nstate = sel ? CH0_5 : CH1_5;  // bev2 + 0.5 / bev1 + 2.0 change
			CH1_5:nstate = CH1_0;                // keep returning 0.5 coins
			CH1_0:nstate = CH0_5;
			CH0_5:nstate = S0;
			default: nstate = S0;
		endcase
	end

	// Moore outputs. Beverage + the first 0.5 coin are emitted on the
	// arriving state; any remaining change is emitted from the CH states.
	always@(*) begin
		if(~rst)
			{out1, out2, out3} = 3'b000;
		else begin
			case(state)
				S1_5: {out1,out2,out3} = sel ? 3'b000 : 3'b100; // bev1
				S2:   {out1,out2,out3} = sel ? 3'b000 : 3'b101; // bev1 + 0.5
				S2_5: {out1,out2,out3} = sel ? 3'b010 : 3'b101; // bev2 / bev1 + 0.5
				S3:   {out1,out2,out3} = sel ? 3'b011 : 3'b101; // bev2+0.5 / bev1+0.5
				S3_5: {out1,out2,out3} = sel ? 3'b011 : 3'b101;
				CH0_5, CH1_0, CH1_5: {out1,out2,out3} = 3'b001;  // change only
				default: {out1,out2,out3} = 3'b000;
			endcase
		end
	end
//*************code***********//
endmodule
