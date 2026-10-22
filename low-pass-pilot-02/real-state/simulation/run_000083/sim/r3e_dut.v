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
//*************code***********//

    localparam S0    = 3'd0;
    localparam S0_5  = 3'd1;
    localparam S1    = 3'd2;
    localparam S1_5  = 3'd3;
    localparam S2    = 3'd4;
    localparam S2_5  = 3'd5;
    localparam S3    = 3'd6;
    localparam CHANGE= 3'd7;

    reg [2:0] state, nstate;
    reg [1:0] change_cnt, nchange_cnt;
    reg [2:0] add;

    always @(*) begin
        nstate = state;
        nchange_cnt = change_cnt;

        if (state == CHANGE) begin
            if (change_cnt == 1) begin
                nstate = S0;
                nchange_cnt = 0;
            end else begin
                nstate = CHANGE;
                nchange_cnt = change_cnt - 1;
            end
        end else begin
            if ( (sel == 0 && state >= S1_5) || (sel == 1 && state >= S2_5) ) begin
                if (sel == 0) begin
                    if (state > S1_5 + 1) begin
                        nstate = CHANGE;
                        nchange_cnt = state - S1_5 - 1;
                    end else begin
                        nstate = S0;
                        nchange_cnt = 0;
                    end
                end else begin
                    nstate = S0;
                    nchange_cnt = 0;
                end
            end else begin
                if (d1 && d2) add = 3;
                else if (d2) add = 2;
                else if (d1) add = 1;
                else add = 0;

                if (state + add > S3)
                    nstate = S3;
                else
                    nstate = state + add;
                nchange_cnt = 0;
            end
        end
    end

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            change_cnt <= 0;
        end else begin
            state <= nstate;
            change_cnt <= nchange_cnt;
        end
    end

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            {out1, out2, out3} <= 3'b000;
        end else begin
            case (state)
                S0, S0_5, S1:  {out1, out2, out3} <= 3'b000;
                S1_5:          {out1, out2, out3} <= (sel == 0) ? 3'b100 : 3'b000;
                S2:            {out1, out2, out3} <= (sel == 0) ? 3'b101 : 3'b000;
                S2_5:          {out1, out2, out3} <= (sel == 0) ? 3'b101 : 3'b010;
                S3:            {out1, out2, out3} <= (sel == 0) ? 3'b101 : 3'b011;
                CHANGE:        {out1, out2, out3} <= 3'b001;
                default:       {out1, out2, out3} <= 3'b000;
            endcase
        end
    end
//*************code***********//
endmodule
