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
    
    wire [3:0] next_clk_cnt = (clk_cnt == (div_flag ? div_o : div_e) - 1) ? 4'd0 : clk_cnt + 4'd1;
    wire [6:0] next_cyc_cnt = (cyc_cnt == M_N - 1) ? 7'd0 : cyc_cnt + 7'd1;
    
    always@(posedge clk_in or negedge rst) begin
        if(~rst)
            clk_cnt <= 4'd0;
        else
            clk_cnt <= next_clk_cnt;
    end
    
    always@(posedge clk_in or negedge rst) begin
        if(~rst) begin
            cyc_cnt <= 7'd0;
            div_flag <= 1'b0;
        end else begin
            cyc_cnt <= next_cyc_cnt;
            if (next_cyc_cnt == (M_N - 1) || next_cyc_cnt == (c89 - 1))
                div_flag <= ~div_flag;
        end
    end
    
    always@(posedge clk_in or negedge rst) begin
        if(~rst)
            clk_out_r <= 1'b0;
        else if(~div_flag)
            clk_out_r <= (next_clk_cnt <= ((div_e>>2)+1));
        else
            clk_out_r <= (next_clk_cnt <= ((div_o>>2)+1));
    end
    
    assign clk_out = clk_out_r;
//*************code***********//
endmodule
