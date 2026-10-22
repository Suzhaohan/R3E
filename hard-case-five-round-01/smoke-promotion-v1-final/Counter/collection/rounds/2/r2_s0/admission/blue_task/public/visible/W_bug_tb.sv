// Self-checking testbench for first_counter.v
// DUT is instantiated in tb, tb will contain a clock generator, reset
// generator, enable logic generator, compare logic.


// step1: create a dummy template that declares inputs to DUT as reg,
// declare outputs of DUT as wire. Note there is no port list for test
// bench.
module tb;
integer sample_index=0, errors=0; reg [4:0] expected;

reg clk, reset, enable;
reg instrument_clk;
wire[3:0] counter_out;
wire overflow_out;


first_counter U0(
    .clk (clk),
    .reset (reset),
    .enable (enable),
    .counter_out (counter_out),
    .overflow_out (overflow_out)
);

// step2: add clock generator logic. Before this we need to drive all
// inputs of DUT to some known state.
initial begin // initial block only executes once 
    clk = 0;
    instrument_clk = 0;
    reset = 0;
    enable = 0;
end

always
    #5 clk = !clk;

always
    #5 instrument_clk = !instrument_clk; // IMPORTANT: Make sure that this reflects the granularity of the oracle w.r.t. the clock cycle!


integer f;
initial begin
    $dumpfile("output_first_counter_tb_t3.vcd");
    $dumpvars();
    f = $fopen("output_first_counter_tb_t3.txt");
    $display("\t\ttime,\tclk,\treset,\tenable,\tcount_out,\toverflow_out\n");
    $fwrite(f, "time,counter_out[3],counter_out[2],counter_out[1],counter_out[0],overflow_out\n");
    $monitor("%d, \t%b, \t%b, \t%b, \t%d, \t\t%b", $time, clk, reset, enable, counter_out, overflow_out);
    forever begin
    @(posedge instrument_clk);
    case(sample_index)
0: expected=5'bxxxxx;
1: expected=5'bxxxxx;
2: expected=5'bxxxxx;
3: expected=5'b00000;
4: expected=5'b00000;
5: expected=5'b00010;
6: expected=5'b00100;
7: expected=5'b00110;
8: expected=5'b01000;
9: expected=5'b01010;
10: expected=5'b01100;
11: expected=5'b01110;
12: expected=5'b10000;
13: expected=5'b10010;
14: expected=5'b10100;
15: expected=5'b10110;
16: expected=5'b11000;
17: expected=5'b11010;
18: expected=5'b11100;
19: expected=5'b11110;
20: expected=5'b00001;
21: expected=5'b00011;
22: expected=5'b00101;
23: expected=5'b00111;
24: expected=5'b01001;
25: expected=5'b01011;
default: begin $display("CHECK_FAIL excess oracle samples"); errors=errors+1; end
endcase
if ({counter_out,overflow_out} !== expected) begin
 $display("CHECK_FAIL oracle sample=%0d got=%b expected=%b",sample_index,{counter_out,overflow_out},expected);
 errors=errors+1;
end
sample_index=sample_index+1;
$fwrite(f, "%g,%b,%b,%b,%b,%b\n", $time, counter_out[3], counter_out[2], counter_out[1], counter_out[0], overflow_out);
    end
end



event reset_trigger;
event reset_done_trigger;
event terminate_sim;


initial begin
    #5
    forever begin
        @(reset_trigger);
        @(negedge clk);
        reset = 1;
        @(negedge clk);
        reset = 0;
        -> reset_done_trigger;
    end
end

initial begin
    @(terminate_sim);
    #5
    $fclose(f);
    $finish;
end

/*
// Test Case 1: Assert/Deassert reset
// trigger the reset_trigger event after 10 time units
initial begin: TEST_CASE_1
    #10 -> reset_trigger;
end
*/



// Test Case 2: Assert/Deassert enable after reset is applied
// trigger the reset logic and wait for it to complete. Then drive
// enable to 1
/*
reg temp_event1;

initial begin
    temp_event1 = 0;
       #10;
    temp_event1 = 1;
end
*/
/*
initial begin: TEST_CASE_2
    #10 -> reset_trigger;
   // @(posedge temp_event1);
    
    @(reset_done_trigger);
    @(negedge clk);
    enable = 1;
    repeat (10) begin
        @(negedge clk);
    end
    enable = 0;
    #5 -> terminate_sim;
end
*/

initial begin: TEST_CASE_4
    #10 -> reset_trigger;
   // @(posedge temp_event1);
    
    @(reset_done_trigger);
    @(negedge clk);
    enable = 1;
    repeat (100) begin
        @(negedge clk);
    end
    enable = 0;
    #5 -> terminate_sim;
end

initial begin
    #253
    
    //@(negedge clk)
    //#5 $display ("Simulation SUCCESS!");
     -> terminate_sim; // terminate simulation after 100 time units.

end


final begin
 if(errors==0 && sample_index==26) $display("TESTBENCH PASS original oracle");
 else $display("CHECK_FAIL oracle errors=%0d samples=%0d",errors,sample_index);
end

endmodule
