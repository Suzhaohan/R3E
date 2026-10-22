module tb;
reg clock=0,reset=1,req_0=0,req_1=0,req_2=0,req_3=0;
wire gnt_0,gnt_1,gnt_2,gnt_3;
fsm_full dut(clock,reset,req_0,req_1,req_2,req_3,gnt_0,gnt_1,gnt_2,gnt_3);
task tick;begin #3;clock=1;#3;clock=0;#3;end endtask
initial begin tick;
if({gnt_0,gnt_1,gnt_2,gnt_3}!==0) begin $display("CHECK_FAIL reset");$finish;end
reset=0;req_0=1;req_1=1;tick;tick;
if({gnt_0,gnt_1,gnt_2,gnt_3}!==4'b1000) begin $display("CHECK_FAIL priority and hold");$finish;end
reset=1;tick;
if({gnt_0,gnt_1,gnt_2,gnt_3}!==0) begin $display("CHECK_FAIL reset grant");$finish;end
$display("TESTBENCH PASS preserve");$finish;
end
endmodule
