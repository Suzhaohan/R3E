module tb;
reg A;
reg B;
reg C;
reg en;
wire [7:0] actual, expected;
decoder_3to8 dut(.A(A),.B(B),.C(C),.en(en),.Y0(actual[0]),.Y1(actual[1]),.Y2(actual[2]),.Y3(actual[3]),.Y4(actual[4]),.Y5(actual[5]),.Y6(actual[6]),.Y7(actual[7]));
r3e_reference oracle(.A(A),.B(B),.C(C),.en(en),.Y0(expected[0]),.Y1(expected[1]),.Y2(expected[2]),.Y3(expected[3]),.Y4(expected[4]),.Y5(expected[5]),.Y6(expected[6]),.Y7(expected[7]));
integer i, fd, bad, first;
initial begin
 fd=$fopen("output.csv","w"); $fdisplay(fd,"time,actual"); bad=0; first=-1;
 for(i=0;i<16;i=i+1) begin
  {A,B,C,en}=i; #1; $fdisplay(fd,"%0d,%b",i,actual);
  if(actual !== expected) begin bad=bad+1; if(first<0) first=i; end
 end
 $fclose(fd);
 if(bad==0) begin
  $display("R3E_ORACLE pass=1 signature=none first=none topology=none");
  $display("R3E_WAVEFORM signal=none first_cycle=none cycle_offset=none relation=none assignment=none cone_depth=none pattern=none");
 end else begin
  $display("R3E_ORACLE pass=0 signature=output_mismatch first=vector%0d topology=actual",first);
  $display("R3E_WAVEFORM signal=actual first_cycle=%0d cycle_offset=0 relation=same_cycle assignment=continuous cone_depth=1 pattern=output_mismatch",first);
 end
 $finish;
end
endmodule
/******************************************************************
 * Date: Aug. 28, 1999
 * File: Decoder 3 to 8.v   (440 Examples)
 *
 * Module of a 3 to 8 Decoder with an active high enable input and
 * and active low outputs. This model uses a trinary continuous 
 * assignment statement for the combinational logic
 *******************************************************************/
//*****************************************************************
  module r3e_reference(Y7, Y6, Y5, Y4, Y3, Y2, Y1, Y0, A, B, C, en);
//*****************************************************************
     output Y7, Y6, Y5, Y4, Y3, Y2, Y1, Y0;
     input  A, B, C;
     input  en;
     assign {Y7,Y6,Y5,Y4,Y3,Y2,Y1,Y0} = ( {en,A,B,C} == 4'b1000) ? 8'b1111_1110 :
                                        ( {en,A,B,C} == 4'b1001) ? 8'b1111_1101 :
                                        ( {en,A,B,C} == 4'b1010) ? 8'b1111_1011 :
                                        ( {en,A,B,C} == 4'b1011) ? 8'b1111_0111 :
                                        ( {en,A,B,C} == 4'b1100) ? 8'b1110_1111 :
                                        ( {en,A,B,C} == 4'b1101) ? 8'b1101_1111 :
                                        ( {en,A,B,C} == 4'b1110) ? 8'b1011_1111 :
                                        ( {en,A,B,C} == 4'b1111) ? 8'b0111_1111 :
                                                                   8'b1111_1111;
  endmodule
