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

    localparam S0 = 2'd0, S1 = 2'd1, S2 = 2'd2;
    reg [1:0] state, nstate;
    reg [4:0] amount;
    reg [4:0] change_counter;

    wire [4:0] price = sel ? 5'd5 : 5'd3;
    wire [4:0] change = amount - price;

    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= S0;
            amount <= 0;
            change_counter <= 0;
        end else begin
            state <= nstate;
            if (state == S1) begin
                amount <= 0;
                if (change > 1)
                    change_counter <= change - 1;
                else
                    change_counter <= 0;
            end else if (state == S0) begin
                if (d1)
                    amount <= amount + 1;
                else if (d2)
                    amount <= amount + 2;
            end else if (state == S2) begin
                change_counter <= change_counter - 1;
            end
        end
    end

    always @(*) begin
        nstate = state;
        case (state)
            S0: begin
                if (amount >= price)
                    nstate = S1;
                else
                    nstate = S0;
            end
            S1: begin
                if (change > 1)
                    nstate = S2;
                else
                    nstate = S0;
            end
            S2: begin
                if (change_counter > 1)
                    nstate = S2;
                else
                    nstate = S0;
            end
            default: nstate = S0;
        endcase
    end

    always @(*) begin
        out1 = 0;
        out2 = 0;
        out3 = 0;
        case (state)
            S1: begin
                if (sel)
                    out2 = 1;
                else
                    out1 = 1;
                if (change > 0)
                    out3 = 1;
            end
            S2: begin
                out3 = 1;
            end
            default: begin
                out1 = 0;
                out2 = 0;
                out3 = 0;
            end
        endcase
    end

endmodule