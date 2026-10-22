module TopModule(
    input wire clk,
    input wire rst,
    input wire d1,
    input wire d2,
    input wire sel,
    output reg out1,
    output reg out2,
    output reg out3
);

    localparam S0     = 4'd0,
               S0_5   = 4'd1,
               S1     = 4'd2,
               S1_5   = 4'd3,
               S2     = 4'd4,
               S2_5   = 4'd5,
               S3     = 4'd6,
               C1     = 4'd7,
               C2     = 4'd8;

    reg [3:0] state;

    always @(posedge clk or negedge rst) begin
        if (~rst)
            state <= S0;
        else begin
            case (state)
                S0: begin
                    if (d1) state <= S0_5;
                    else if (d2) state <= S1;
                    else state <= S0;
                end
                S0_5: begin
                    if (d1) state <= S1;
                    else if (d2) state <= S1_5;
                    else state <= S0_5;
                end
                S1: begin
                    if (d1) state <= S1_5;
                    else if (d2) state <= S2;
                    else state <= S1;
                end
                S1_5: begin
                    if (~sel) state <= S0;
                    else if (d1) state <= S2;
                    else if (d2) state <= S2_5;
                    else state <= S1_5;
                end
                S2: begin
                    if (~sel) state <= S0;
                    else if (d1) state <= S2_5;
                    else if (d2) state <= S3;
                    else state <= S2;
                end
                S2_5: begin
                    if (~sel) state <= C1;
                    else state <= S0;
                end
                S3: begin
                    if (~sel) state <= C2;
                    else state <= S0;
                end
                C1: state <= S0;
                C2: state <= C1;
                default: state <= S0;
            endcase
        end
    end

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            {out1, out2, out3} <= 3'b000;
        end else begin
            case (state)
                S0, S0_5, S1: {out1, out2, out3} <= 3'b000;
                S1_5:          {out1, out2, out3} <= (~sel) ? 3'b100 : 3'b000;
                S2:            {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b000;
                S2_5:          {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b010;
                S3:            {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b011;
                C1, C2:        {out1, out2, out3} <= 3'b001;
                default:       {out1, out2, out3} <= 3'b000;
            endcase
        end
    end

endmodule
