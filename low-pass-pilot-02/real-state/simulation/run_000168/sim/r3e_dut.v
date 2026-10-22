module TopModule(
     input  wire clk_in,
     input  wire rst,
     output wire clk_out
);
    parameter M_N = 8'd87; 
    parameter c89 = 8'd24;  // 8/9 clock switching point
    parameter div_e = 5'd8; //Even period
    parameter div_o = 5'd9; //Odd period

    reg [6:0] cyc_cnt;
    reg [3:0] clk_cnt;
    wire div_flag;

    assign div_flag = (cyc_cnt >= c89);

    always @(posedge clk_in or negedge rst) begin
        if (~rst)
            cyc_cnt <= 0;
        else if (cyc_cnt == M_N - 1)
            cyc_cnt <= 0;
        else
            cyc_cnt <= cyc_cnt + 1;
    end

    always @(posedge clk_in or negedge rst) begin
        if (~rst)
            clk_cnt <= 0;
        else if (div_flag == 1'b0) begin
            if (clk_cnt == div_e - 1)
                clk_cnt <= 0;
            else
                clk_cnt <= clk_cnt + 1;
        end else begin
            if (clk_cnt == div_o - 1)
                clk_cnt <= 0;
            else
                clk_cnt <= clk_cnt + 1;
        end
    end

    assign clk_out = (~rst) ? 1'b0 : (clk_cnt < 4) ? 1'b1 : 1'b0;

endmodule
