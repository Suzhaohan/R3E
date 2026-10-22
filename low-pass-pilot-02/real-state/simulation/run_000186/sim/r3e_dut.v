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

    parameter S0=0, S0_5=1, S1=2, S1_5=3, S2=4, S2_5=5, S3=6, S_CHG1=7, S_CHG2=8;
    reg[3:0] state, nstate;
    reg[3:0] total, cost, add, new_total;
    
    always@(posedge clk or negedge rst) begin
        if(~rst)
            state <= S0;
        else
            state <= nstate;
    end
    
    always@(*) begin
        nstate = state; // default hold
        case(state)
            S0, S0_5, S1, S1_5, S2, S2_5, S3: begin
                case(state)
                    S0: total = 0;
                    S0_5: total = 1;
                    S1: total = 2;
                    S1_5: total = 3;
                    S2: total = 4;
                    S2_5: total = 5;
                    S3: total = 6;
                    default: total = 0;
                endcase
                cost = sel ? 5 : 3;
                if (total >= cost) begin
                    case(state)
                        S1_5: if (!sel) nstate = S0;
                        S2:   if (!sel) nstate = S0;
                        S2_5: if (!sel) nstate = S_CHG1; else nstate = S0;
                        S3:   if (!sel) nstate = S_CHG2; else nstate = S0;
                        default: nstate = S0;
                    endcase
                end else begin
                    if (d1 && !d2) add = 1;
                    else if (d2 && !d1) add = 2;
                    else add = 0;
                    new_total = total + add;
                    case(new_total)
                        0: nstate = S0;
                        1: nstate = S0_5;
                        2: nstate = S1;
                        3: nstate = S1_5;
                        4: nstate = S2;
                        5: nstate = S2_5;
                        6: nstate = S3;
                        default: nstate = S0;
                    endcase
                end
            end
            S_CHG1: nstate = S0;
            S_CHG2: nstate = S_CHG1;
            default: nstate = S0;
        endcase
    end
    
    always @(posedge clk or negedge rst) begin
      if (~rst) begin
        {out1, out2, out3} <= 3'b000;
      end
      else begin
        case (state)
          S0, S0_5, S1:  {out1, out2, out3} <= 3'b000;
          S1_5:          {out1, out2, out3} <= (~sel) ? 3'b100 : 3'b000;
          S2:            {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b000;
          S2_5:          {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b010;
          S3:            {out1, out2, out3} <= (~sel) ? 3'b101 : 3'b011;
          S_CHG1:        {out1, out2, out3} <= 3'b001;
          S_CHG2:        {out1, out2, out3} <= 3'b001;
          default:        {out1, out2, out3} <= 3'b000;
        endcase
      end
    end
//*************code***********//
endmodule
