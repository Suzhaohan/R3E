module TopModule(
	input clk,
	input rst_n,
	input a,
	output match
	);

	reg [7:0] a_tem;

	always @(posedge clk or negedge rst_n)
		if (!rst_n)
			begin
				a_tem <= 8'b0;
			end
		else
			begin
				a_tem <= {a_tem[6:0], a};
			end

	assign match = (a_tem == 8'b0111_0001);

endmodule
