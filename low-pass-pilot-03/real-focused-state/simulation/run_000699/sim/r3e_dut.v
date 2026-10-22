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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, DISP=7;
    reg [2:0] state, nstate;
    reg change_mode, nchange_mode;
    reg [1:0] change, nchange;
    reg [2:0] new_amount;
    reg [2:0] price;
    
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            change_mode <= 0;
            change <= 0;
        end else begin
            state <= nstate;
            change_mode <= nchange_mode;
            change <= nchange;
        end
    end
    
    always @(*) begin
        nstate = state;
        nchange_mode = change_mode;
        nchange = change;
        
        if (change_mode) begin
            if (state == S0) begin
                nstate = S0;
                nchange_mode = 0;
            end else if (state == S0_5) begin
                nstate = S0;
                nchange_mode = 0;
            end else begin
                nstate = state - 1;
                nchange_mode = 1;
            end
        end else if (state == DISP) begin
            if (change > 1) begin
                nstate = change - 1;
                nchange_mode = 1;
            end else begin
                nstate = S0;
                nchange_mode = 0;
            end
            nchange = 0;
        end else begin
            if (d1) new_amount = state + 1;
            else if (d2) new_amount = state + 2;
            else new_amount = state;
            
            price = sel ? 5 : 3;
            if (new_amount >= price) begin
                nstate = DISP;
                nchange = new_amount - price;
                nchange_mode = 0;
            end else begin
                nstate = new_amount;
                nchange = 0;
                nchange_mode = 0;
            end
        end
    end
    
    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        if (change_mode) begin
            if (state != S0) out3 = 1;
        end else if (state == DISP) begin
            if (sel == 0) out1 = 1;
            else out2 = 1;
            if (change > 0) out3 = 1;
        end
    end
    
endmodule
