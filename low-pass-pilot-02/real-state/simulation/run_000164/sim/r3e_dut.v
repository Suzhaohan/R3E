module TopModule(
     input  wire clk_in,
     input  wire rst,
     output wire clk_out
);
    parameter M_N = 8'd87; 
    parameter c89 = 8'd24;
    parameter div_e = 5'd8;
    parameter div_o = 5'd9;

    reg [3:0] clk_cnt;
    reg [6:0] cyc_cnt;
    reg div_flag;

    always @(posedge clk_in or negedge rst) begin
        if (~rst) begin
            clk_cnt <= 0;
            div_flag <= 0;
        end else begin
            if (~div_flag) begin
                if (clk_cnt == div_e - 1) begin
                    clk_cnt <= 0;
                    if (cyc_cnt == c89 - 1)
                        div_flag <= 1;
                    else if (cyc_cnt == M_N - 1)
                        div_flag <= 0;
                end else
                    clk_cnt <= clk_cnt + 1;
            end else begin
                if (clk_cnt == div_o - 1) begin
                    clk_cnt <= 0;
                    if (cyc_cnt == c89 - 1)
                        div_flag <= 1;
                    else if (cyc_cnt == M_N - 1)
                        div_flag <= 0;
                end else
                    clk_cnt <= clk_cnt + 1;
            end
        end
    end

    always @(posedge clk_in or negedge rst) begin
        if (~rst)
            cyc_cnt <= 0;
        else
            cyc_cnt <= (cyc_cnt == M_N - 1) ? 0 : cyc_cnt + 1;
    end

    assign clk_out = (clk_cnt <= ((div_flag ? div_o : div_e) >> 2) + 1);

endmodule
