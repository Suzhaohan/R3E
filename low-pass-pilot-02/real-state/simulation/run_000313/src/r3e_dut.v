module TopModule(
	input clk,
	input rst_n,
	input a,
	output match
	);

	reg [8:0] a_tem;

	// 9-bit shift register: newest input bit enters the MSB
	always @(posedge clk or negedge rst_n)
		if (!rst_n)
			begin
				a_tem <= 9'b0;
			end
		else
			begin
				a_tem <= {a, a_tem[7:0]};
			end

	// Combinational detection of the pattern "011XXX110" directly from the
	// current shift-register contents (no extra output pipeline register).
	assign match = (a_tem[8:6] == 3'b011) && (a_tem[2:0] == 3'b110);

endmodule
