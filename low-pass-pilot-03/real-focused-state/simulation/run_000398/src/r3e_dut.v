module TopModule(
    input clk,
    input rst_n,
    input a,
    output reg match
);

    reg [7:0] a_tem;
    wire [7:0] next_a_tem = {a_tem[6:0], a};

    always @(posedge clk or negedge rst_n)
        if (!rst_n) begin
            a_tem <= 8'b0;
            match <= 1'b0;
        end else begin
            a_tem <= next_a_tem;
            match <= (next_a_tem == 8'b0111_0001);
        end

endmodule
