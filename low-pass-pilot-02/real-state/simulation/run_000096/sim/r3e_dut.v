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

    localparam S0 = 4'd0,
               S0_5 = 4'd1,
               S1 = 4'd2,
               S1_5 = 4'd3,
               S2 = 4'd4,
               S2_5 = 4'd5,
               S3 = 4'd6,
               CH0_5 = 4'd7,
               CH1_0 = 4'd8;

    reg [3:0] state, nstate;

    always @(posedge clk or negedge rst) begin
        if (!rst)
            state <= S0;
        else
            state <= nstate;
    end

    always @(*) begin
        case (state)
            S0: begin
                if (d1) nstate = S0_5;
                else if (d2) nstate = S1;
                else nstate = S0;
            end
            S0_5: begin
                if (d1) nstate = S1;
                else if (d2) nstate = S1_5;
                else nstate = S0_5;
            end
            S1: begin
                if (d1) nstate = S1_5;
                else if (d2) nstate = S2;
                else nstate = S1;
            end
            S1_5: begin
                if (~sel) nstate = S0;
                else if (d1) nstate = S2;
                else if (d2) nstate = S2_5;
                else nstate = S1_5;
            end
            S2: begin
                if (~sel) nstate = S0;
                else if (d1) nstate = S2_5;
                else if (d2) nstate = S3;
                else nstate = S2;
            end
            S2_5: begin
                if (sel) nstate = S0;
                else nstate = CH0_5;
            end
            S3: begin
                if (sel) nstate = S0;
                else nstate = CH1_0;
            end
            CH0_5: nstate = S0;
            CH1_0: nstate = CH0_5;
            default: nstate = S0;
        endcase
    end

    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        case (state)
            S1_5: if (~sel) out1 = 1;
            S2: if (~sel) begin out1 = 1; out3 = 1; end
            S2_5: begin
                if (sel) out2 = 1;
                else begin out1 = 1; out3 = 1; end
            end
            S3: begin
                if (sel) begin out2 = 1; out3 = 1; end
                else begin out1 = 1; out3 = 1; end
            end
            CH0_5: out3 = 1;
            CH1_0: out3 = 1;
            default: begin out1 = 0; out2 = 0; out3 = 0; end
        endcase
    end

endmodule
