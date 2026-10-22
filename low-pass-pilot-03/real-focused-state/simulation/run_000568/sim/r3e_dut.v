module TopModule(
	input wire clk  ,
	input wire rst  ,
	input wire d1 ,
	input wire d2 ,
	input wire sel ,
	
	output reg out1,
	output reg out2,
	output reg out3
);
//*************code***********//

    // States
    localparam IDLE = 2'd0;
    localparam DISPENSE_BEV = 2'd1;
    localparam DISPENSE_CHANGE = 2'd2;

    reg [1:0] state, next_state;
    reg [3:0] money, next_money;
    reg [3:0] change, next_change;

    // Price in half-yuan units
    wire [3:0] price = (sel == 1'b0) ? 4'd3 : 4'd5; // 1.5 or 2.5

    // Sequential logic
    always @(posedge clk or negedge rst) begin
        if (~rst) begin
            state <= IDLE;
            money <= 4'd0;
            change <= 4'd0;
        end else begin
            state <= next_state;
            money <= next_money;
            change <= next_change;
        end
    end

    // Combinational next-state and output logic
    always @(*) begin
        // Defaults
        next_state = state;
        next_money = money;
        next_change = change;
        out1 = 1'b0;
        out2 = 1'b0;
        out3 = 1'b0;

        case (state)
            IDLE: begin
                if (money >= price) begin
                    next_state = DISPENSE_BEV;
                end else begin
                    // Add money based on d1, d2
                    if (d1 && d2)
                        next_money = money + 4'd3;
                    else if (d1)
                        next_money = money + 4'd1;
                    else if (d2)
                        next_money = money + 4'd2;
                    else
                        next_money = money;
                    next_state = IDLE;
                end
            end
            DISPENSE_BEV: begin
                // Output beverage
                if (sel == 1'b0)
                    out1 = 1'b1;
                else
                    out2 = 1'b1;
                // Compute change
                next_change = money - price;
                if (next_change == 4'd0) begin
                    next_state = IDLE;
                    next_money = 4'd0;
                end else begin
                    next_state = DISPENSE_CHANGE;
                    next_money = 4'd0;
                end
            end
            DISPENSE_CHANGE: begin
                if (change > 4'd0) begin
                    out3 = 1'b1;
                    next_change = change - 4'd1;
                    if (next_change == 4'd0) begin
                        next_state = IDLE;
                        next_money = 4'd0;
                    end else begin
                        next_state = DISPENSE_CHANGE;
                        next_money = 4'd0;
                    end
                end else begin
                    next_state = IDLE;
                    next_money = 4'd0;
                end
            end
            default: begin
                next_state = IDLE;
                next_money = 4'd0;
                next_change = 4'd0;
            end
        endcase
    end

//*************code***********//
endmodule
