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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6;
    reg [2:0] state, nstate;
    reg [3:0] add, next_amount;

    always @(posedge clk or negedge rst) begin
        if (!rst)
            state <= S0;
        else
            state <= nstate;
    end

    always @(*) begin
        add = (d1 ? 1 : 0) + (d2 ? 2 : 0);
        next_amount = state + add;
        if (sel == 0) begin
            if (state >= S1_5)
                nstate = S0;
            else if (next_amount > S3)
                nstate = S3;
            else
                nstate = next_amount[2:0];
        end else begin
            if (state >= S2_5)
                nstate = S0;
            else if (next_amount > S3)
                nstate = S3;
            else
                nstate = next_amount[2:0];
        end
    end

    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        if (rst) begin
            if (sel == 0) begin
                if (state >= S1_5) begin
                    out1 = 1;
                    out3 = (state > S1_5);
                end
            end else begin
                if (state >= S2_5) begin
                    out2 = 1;
                    out3 = (state > S2_5);
                end
            end
        end
    end

endmodule
