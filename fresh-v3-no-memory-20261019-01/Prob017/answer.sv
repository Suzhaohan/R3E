module TopModule(
     input  wire clk_in,
     input  wire rst,
     output wire clk_out
);
    parameter M_N = 8'd87; 
    parameter c89 = 8'd24;  
    parameter div_e = 5'd8;
    parameter div_o = 5'd9;

    reg [3:0] count;
    reg [6:0] cycle_count;
    reg mode;
    reg clk_out_reg;

    always @(posedge clk_in or negedge rst) begin
        if (~rst) begin
            count <= 4'b0;
            cycle_count <= 7'b0;
            mode <= 1'b0;
            clk_out_reg <= 1'b0;
        end else begin
            // Update output clock
            clk_out_reg <= (count <= ((mode ? div_o : div_e) / 4) + 1);

            // Update count
            if (count == (mode ? div_o : div_e) - 1) begin
                count <= 4'b0;
            end else begin
                count <= count + 1;
            end

            // Update mode
            if (cycle_count == M_N - 1 || cycle_count == c89 - 1) begin
                mode <= ~mode;
            end

            // Update cycle_count
            if (cycle_count == M_N - 1) begin
                cycle_count <= 7'b0;
            end else begin
                cycle_count <= cycle_count + 1;
            end
        end
    end

    assign clk_out = clk_out_reg;
endmodule