module TopModule(
     input  wire clk_in,
     input  wire rst,
     output wire clk_out
);
    parameter M_N = 8'd87; 
    parameter c89 = 8'd24;  // 8/9 clock switching point
    parameter div_e = 5'd8; //Even period
    parameter div_o = 5'd9; //Odd period

    reg [3:0] clk_cnt;
    reg [6:0] cyc_cnt;
    reg div_flag;
    reg clk_out_r;

    always @(posedge clk_in or negedge rst) begin
        if (!rst) begin
            clk_cnt <= 0;
            cyc_cnt <= 0;
            div_flag <= 0;
            clk_out_r <= 0;
        end else begin
            // cyc_cnt counter
            if (cyc_cnt == M_N - 1)
                cyc_cnt <= 0;
            else
                cyc_cnt <= cyc_cnt + 1;

            // clk_cnt counter and div_flag update
            if (clk_cnt == (div_flag ? div_o : div_e) - 1) begin
                clk_cnt <= 0;
                // update div_flag for next output period
                if ((cyc_cnt == M_N - 1) ? 0 : (cyc_cnt + 1) >= c89)
                    div_flag <= 1;
                else
                    div_flag <= 0;
            end else begin
                clk_cnt <= clk_cnt + 1;
            end

            // clk_out_r generation
            if (div_flag)
                clk_out_r <= (clk_cnt <= ((div_o >> 2) + 1));
            else
                clk_out_r <= (clk_cnt <= ((div_e >> 2) + 1));
        end
    end

    assign clk_out = clk_out_r;
endmodule
