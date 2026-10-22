`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
	input clk,
    // === Start your code here ===
	output logic rst,
	output logic d1,
	output logic d2,
	output logic sel
    // === End your code here ===
);
	// === Start your code here ===
	initial begin
		rst = 0;
		d1 = 0;
		d2 = 0;
		sel = 0;
		repeat(10) @(posedge clk);
		rst = 1;
		@(posedge clk);
		
		// Test case 1: Insert 1.5 yuan and select beverage 1 (sel=0)
		d1 = 1; @(posedge clk);  // Insert 0.5 yuan
		d1 = 0; @(posedge clk);
		d1 = 1; @(posedge clk);  // Insert another 0.5 yuan
		d1 = 0; @(posedge clk);
		d1 = 1; @(posedge clk);  // Insert third 0.5 yuan
		d1 = 0; @(posedge clk);
		sel = 0; @(posedge clk);  // Select beverage 1
		sel = 0; @(posedge clk);  // Should dispense beverage 1
		
		// Test case 2: Insert 2.5 yuan and select beverage 2 (sel=1)
		d2 = 1; @(posedge clk);  // Insert 1 yuan
		d2 = 0; @(posedge clk);
		d2 = 1; @(posedge clk);  // Insert another 1 yuan
		d2 = 0; @(posedge clk);
		d1 = 1; @(posedge clk);  // Insert 0.5 yuan
		d1 = 0; @(posedge clk);
		sel = 1; @(posedge clk);  // Select beverage 2
		sel = 1; @(posedge clk);  // Should dispense beverage 2
		
		// Test case 3: Insert 2 yuan and select beverage 1 (sel=0) - should get change
		d2 = 1; @(posedge clk);  // Insert 1 yuan
		d2 = 0; @(posedge clk);
		d2 = 1; @(posedge clk);  // Insert another 1 yuan
		d2 = 0; @(posedge clk);
		sel = 0; @(posedge clk);  // Select beverage 1
		sel = 0; @(posedge clk);  // Should dispense beverage 1 + 0.5 yuan change
		
		// Test case 4: Insert 3 yuan and select beverage 2 (sel=1) - should get change
		d2 = 1; @(posedge clk);  // Insert 1 yuan
		d2 = 0; @(posedge clk);
		d2 = 1; @(posedge clk);  // Insert another 1 yuan
		d2 = 0; @(posedge clk);
		d2 = 1; @(posedge clk);  // Insert third 1 yuan
		d2 = 0; @(posedge clk);
		sel = 1; @(posedge clk);  // Select beverage 2
		sel = 1; @(posedge clk);  // Should dispense beverage 2 + 0.5 yuan change
		
		// Random testing
		repeat(100) @(posedge clk, negedge clk) begin
			d1 <= $random;
			d2 <= $random;
			sel <= $random;
		end
		
		#1 $finish;
	end
	// === End your code here ===
	
endmodule

module tb();

	// === Start your code here ===
	typedef struct packed {
		int errors;
		int errortime;
		int errors_out1;
		int errortime_out1;
		int errors_out2;
		int errortime_out2;
		int errors_out3;
		int errortime_out3;

		int clocks;
	} stats;
	// === End your code here ===
	
	stats stats1;
reg [2:0] expected [0:180];
initial begin
expected[0]=3'b000;
expected[1]=3'b000;
expected[2]=3'b000;
expected[3]=3'b000;
expected[4]=3'b000;
expected[5]=3'b000;
expected[6]=3'b000;
expected[7]=3'b000;
expected[8]=3'b000;
expected[9]=3'b000;
expected[10]=3'b000;
expected[11]=3'b000;
expected[12]=3'b000;
expected[13]=3'b000;
expected[14]=3'b000;
expected[15]=3'b000;
expected[16]=3'b000;
expected[17]=3'b000;
expected[18]=3'b000;
expected[19]=3'b000;
expected[20]=3'b000;
expected[21]=3'b000;
expected[22]=3'b000;
expected[23]=3'b000;
expected[24]=3'b000;
expected[25]=3'b000;
expected[26]=3'b000;
expected[27]=3'b000;
expected[28]=3'b000;
expected[29]=3'b000;
expected[30]=3'b000;
expected[31]=3'b100;
expected[32]=3'b100;
expected[33]=3'b000;
expected[34]=3'b000;
expected[35]=3'b000;
expected[36]=3'b000;
expected[37]=3'b000;
expected[38]=3'b000;
expected[39]=3'b000;
expected[40]=3'b000;
expected[41]=3'b000;
expected[42]=3'b000;
expected[43]=3'b101;
expected[44]=3'b101;
expected[45]=3'b000;
expected[46]=3'b000;
expected[47]=3'b000;
expected[48]=3'b000;
expected[49]=3'b000;
expected[50]=3'b000;
expected[51]=3'b000;
expected[52]=3'b000;
expected[53]=3'b000;
expected[54]=3'b000;
expected[55]=3'b000;
expected[56]=3'b000;
expected[57]=3'b000;
expected[58]=3'b000;
expected[59]=3'b010;
expected[60]=3'b010;
expected[61]=3'b000;
expected[62]=3'b000;
expected[63]=3'b000;
expected[64]=3'b000;
expected[65]=3'b000;
expected[66]=3'b000;
expected[67]=3'b000;
expected[68]=3'b000;
expected[69]=3'b000;
expected[70]=3'b000;
expected[71]=3'b101;
expected[72]=3'b101;
expected[73]=3'b000;
expected[74]=3'b000;
expected[75]=3'b000;
expected[76]=3'b000;
expected[77]=3'b000;
expected[78]=3'b000;
expected[79]=3'b000;
expected[80]=3'b000;
expected[81]=3'b000;
expected[82]=3'b000;
expected[83]=3'b000;
expected[84]=3'b000;
expected[85]=3'b010;
expected[86]=3'b010;
expected[87]=3'b000;
expected[88]=3'b000;
expected[89]=3'b000;
expected[90]=3'b000;
expected[91]=3'b000;
expected[92]=3'b100;
expected[93]=3'b000;
expected[94]=3'b000;
expected[95]=3'b000;
expected[96]=3'b000;
expected[97]=3'b100;
expected[98]=3'b100;
expected[99]=3'b000;
expected[100]=3'b000;
expected[101]=3'b000;
expected[102]=3'b000;
expected[103]=3'b000;
expected[104]=3'b000;
expected[105]=3'b000;
expected[106]=3'b000;
expected[107]=3'b000;
expected[108]=3'b000;
expected[109]=3'b101;
expected[110]=3'b101;
expected[111]=3'b000;
expected[112]=3'b000;
expected[113]=3'b000;
expected[114]=3'b000;
expected[115]=3'b000;
expected[116]=3'b000;
expected[117]=3'b100;
expected[118]=3'b000;
expected[119]=3'b000;
expected[120]=3'b000;
expected[121]=3'b000;
expected[122]=3'b000;
expected[123]=3'b000;
expected[124]=3'b000;
expected[125]=3'b100;
expected[126]=3'b000;
expected[127]=3'b000;
expected[128]=3'b000;
expected[129]=3'b000;
expected[130]=3'b000;
expected[131]=3'b000;
expected[132]=3'b100;
expected[133]=3'b000;
expected[134]=3'b000;
expected[135]=3'b000;
expected[136]=3'b000;
expected[137]=3'b000;
expected[138]=3'b000;
expected[139]=3'b000;
expected[140]=3'b000;
expected[141]=3'b100;
expected[142]=3'b000;
expected[143]=3'b101;
expected[144]=3'b000;
expected[145]=3'b000;
expected[146]=3'b000;
expected[147]=3'b000;
expected[148]=3'b000;
expected[149]=3'b000;
expected[150]=3'b000;
expected[151]=3'b000;
expected[152]=3'b101;
expected[153]=3'b000;
expected[154]=3'b000;
expected[155]=3'b000;
expected[156]=3'b000;
expected[157]=3'b000;
expected[158]=3'b000;
expected[159]=3'b000;
expected[160]=3'b000;
expected[161]=3'b100;
expected[162]=3'b100;
expected[163]=3'b000;
expected[164]=3'b000;
expected[165]=3'b000;
expected[166]=3'b000;
expected[167]=3'b100;
expected[168]=3'b100;
expected[169]=3'b000;
expected[170]=3'b000;
expected[171]=3'b000;
expected[172]=3'b000;
expected[173]=3'b000;
expected[174]=3'b000;
expected[175]=3'b101;
expected[176]=3'b000;
expected[177]=3'b101;
expected[178]=3'b010;
expected[179]=3'b000;
expected[180]=3'b000;
end

	
	
	wire[511:0] wavedrom_title;
	wire wavedrom_enable;
	int wavedrom_hide_after_time;
	
	reg clk=0;
	initial forever
		#5 clk = ~clk;

	// === Start your code here ===
	logic rst;
	logic d1;
	logic d2;
	logic sel;
	logic out1_ref;
	logic out2_ref;
	logic out3_ref;
	logic out1_dut;
	logic out2_dut;
	logic out3_dut;
	// === End your code here ===

	initial begin 
		// R3E: waveform dump disabled; use the visible CSV trace.
		// === Start your code here ===
		// R3E: waveform dump disabled; use the visible CSV trace.
		// === End your code here ===
	end


	wire tb_match;		// Verification
	wire tb_mismatch = ~tb_match;
	
	// === Start your code here ===
	stimulus_gen stim1 (
		.clk,
		.rst,
		.d1,
		.d2,
		.sel );
		
	
		
	TopModule top_module1 (
		.clk,
		.rst,
		.d1,
		.d2,
		.sel,
		.out1(out1_dut),
		.out2(out2_dut),
		.out3(out3_dut) );
	// === End your code here ===

	
	bit strobe = 0;
	task wait_for_end_of_timestep;
		repeat(5) begin
			strobe <= !strobe;  // Try to delay until the very end of the time step.
			@(strobe);
		end
	endtask	

	
	final begin
		// === Start your code here ===
		if (stats1.errors_out1) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "out1", stats1.errors_out1, stats1.errortime_out1);
		else $display("Hint: Output '%s' has no mismatches.", "out1");
		if (stats1.errors_out2) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "out2", stats1.errors_out2, stats1.errortime_out2);
		else $display("Hint: Output '%s' has no mismatches.", "out2");
		if (stats1.errors_out3) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "out3", stats1.errors_out3, stats1.errortime_out3);
		else $display("Hint: Output '%s' has no mismatches.", "out3");
        // === End your code here ===

		$display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
		$display("Simulation finished at %0d ps", $time);
		$display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
if(stats1.errors==0 && stats1.clocks==181) $display("TESTBENCH PASS original samples"); else $display("CHECK_FAIL original samples");
	end
	
	// Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
	assign tb_match = ( { out1_ref, out2_ref, out3_ref } === ( { out1_ref, out2_ref, out3_ref } ^ { out1_dut, out2_dut, out3_dut } ^ { out1_ref, out2_ref, out3_ref } ) );
	// Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
	// the sensitivity list of the @(strobe) process, which isn't implemented.
	always @(posedge clk, negedge clk) begin

		{out1_ref,out2_ref,out3_ref}=expected[stats1.clocks];
 stats1.clocks++;
		if (!({out1_ref,out2_ref,out3_ref} === ({out1_ref,out2_ref,out3_ref}^{out1_dut,out2_dut,out3_dut}^{out1_ref,out2_ref,out3_ref}))) begin
			if (stats1.errors == 0) stats1.errortime = $time;
			stats1.errors++;
		end
		// === Start your code here ===
		if (out1_ref !== ( out1_ref ^ out1_dut ^ out1_ref ))
		begin if (stats1.errors_out1 == 0) stats1.errortime_out1 = $time;
			stats1.errors_out1 = stats1.errors_out1+1'b1; end
		if (out2_ref !== ( out2_ref ^ out2_dut ^ out2_ref ))
		begin if (stats1.errors_out2 == 0) stats1.errortime_out2 = $time;
			stats1.errors_out2 = stats1.errors_out2+1'b1; end
		if (out3_ref !== ( out3_ref ^ out3_dut ^ out3_ref ))
		begin if (stats1.errors_out3 == 0) stats1.errortime_out3 = $time;
			stats1.errors_out3 = stats1.errors_out3+1'b1; end
         // === End your code here ===

	end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end


    // R3E visible output trace; one binary digit per DUT output bit.
    // Preserve upstream stimuli/checker. Sample after NBA updates settle.
    integer r3e_trace_fd, r3e_stimulus_fd, r3e_stimulation_fd;
    initial begin
        r3e_trace_fd = $fopen("trace_visible.txt", "w");
        if (r3e_trace_fd == 0) $fatal(1, "Cannot open trace_visible.txt");
        $fdisplay(r3e_trace_fd, "time,out1,out2,out3");
        r3e_stimulus_fd = $fopen("stimulus_visible.txt", "w");
        r3e_stimulation_fd = $fopen("stimulation_visible.txt", "w");
        if (r3e_stimulus_fd == 0 || r3e_stimulation_fd == 0)
            $fatal(1, "Cannot open visible input logs");
        $fdisplay(r3e_stimulus_fd, "# Inputs sampled after NBA on both tb.clk edges, row-aligned with trace_visible.txt; clocks and resets included");
        $fdisplay(r3e_stimulation_fd, "# Inputs sampled after NBA on both tb.clk edges, row-aligned with trace_visible.txt; clocks and resets included");
        $fdisplay(r3e_stimulus_fd, "time,clk,rst,d1,d2,sel");
        $fdisplay(r3e_stimulation_fd, "time,clk,rst,d1,d2,sel");
    end
    always @(posedge clk or negedge clk) begin
        $fstrobe(r3e_trace_fd, "%0t,%b,%b,%b", $time, out1_dut, out2_dut, out3_dut);
        $fstrobe(r3e_stimulus_fd, "%0t,%b,%b,%b,%b,%b", $time, clk, rst, d1, d2, sel);
        $fstrobe(r3e_stimulation_fd, "%0t,%b,%b,%b,%b,%b", $time, clk, rst, d1, d2, sel);
    end
    // Simulator exit flushes/closes the file. Closing it in a final block
    // could discard a pending postponed-region sample on the last edge.

endmodule
