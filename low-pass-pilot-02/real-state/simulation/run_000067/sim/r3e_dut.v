module TopModule(
     input  wire clk_in,
     input  wire rst,
     output wire clk_out
);
    parameter M_N = 8'd87; 
    parameter c89 = 8'd24;  // 8/9 clock switching point
    parameter div_e = 5'd8; //Even period
    parameter div_o = 5'd9; //Odd period
//*************code***********//
    reg [3:0] clk_cnt;
    reg [6:0] cyc_cnt;
    reg div_flag;
    reg clk_out_r;
    
    wire [3:0] clk_cnt_next;
    wire [6:0] cyc_cnt_next;
    
    assign clk_cnt_next = div_flag ? (clk_cnt == div_o-1 ? 0 : clk_cnt+1) : (clk_cnt == div_e-1 ? 0 : clk_cnt+1);
    assign cyc_cnt_next = (cyc_cnt == M_N-1) ? 0 : cyc_cnt+1;
    
    always @(posedge clk_in or negedge rst) begin
        if (~rst) begin
            clk_cnt <= 0;
            cyc_cnt <= 0;
            div_flag <= 0;
            clk_out_r <= 0;
        end else begin
            clk_cnt <= clk_cnt_next;
            cyc_cnt <= cyc_cnt_next;
            if (cyc_cnt == c89-1 || cyc_cnt == M_N-1)
                div_flag <= ~div_flag;
            clk_out_r <= (clk_cnt_next <= ((div_flag ? div_o : div_e) >> 2) + 1);
        end
    end
    
    assign clk_out = clk_out_r;
//*************code***********//
endmodule
