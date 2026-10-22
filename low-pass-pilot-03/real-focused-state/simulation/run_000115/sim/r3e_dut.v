module TopModule(
    input clk,
    input rst_n,
    input a,
    output reg match
    );

    reg [7:0] a_tem;

    always @(posedge clk or negedge rst_n)
        if (!rst_n)
            a_tem <= 8'b0;
        else
            a_tem <= {a_tem[6:0], a};

    always @(*)
        if (!rst_n)
            match = 1'b0;
        else if (a_tem == 8'b0111_0001)
            match = 1'b1;
        else
            match = 1'b0;

endmodule
