module first_counter(
    clk,
    reset,
    enable,
    counter_out,
    overflow_out
);

input clk;
input reset;
input enable;

output[3:0] counter_out;
output overflow_out;

wire clk;
wire reset;
wire enable;

reg[3:0] counter_out;
reg overflow_out;

always @(posedge clk)
begin: COUNTER
    if(reset == 1'b1) begin
        counter_out <= 4'b0000;
        overflow_out <= 1'b0;
    end
    else if(enable == 1'b1) begin
        if(counter_out == 4'b1111) begin
            counter_out <= 4'b0000;
            overflow_out <= 1'b1;
        end
        else begin
            counter_out <= counter_out + 4'b0001;
            overflow_out <= 1'b0;
        end
    end
    else begin
        overflow_out <= 1'b0;
    end
end

endmodule
