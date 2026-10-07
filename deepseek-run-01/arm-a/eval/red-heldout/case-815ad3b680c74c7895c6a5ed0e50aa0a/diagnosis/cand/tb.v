module tb;
 reg [3:0] a,b; wire y; integer i,j,fd,bad,first;
 m dut(.a(a),.b(b),.y(y));
 initial begin
 fd=$fopen("output.csv","w"); $fdisplay(fd,"time,y"); bad=0; first=-1;
 for(i=0;i<16;i=i+1) begin for(j=0;j<16;j=j+1) begin
 a=i; b=j; #1; $fdisplay(fd,"%0d,%b",i*16+j,y);
 if(y !== ((a < 4) || (b > 13))) begin bad=bad+1; if(first<0) first=i*16+j; end
 end end
 $fclose(fd);
 if(bad==0) begin
 $display("R3E_ORACLE pass=1 signature=none first=none topology=none");
 $display("R3E_WAVEFORM signal=none first_cycle=none cycle_offset=none relation=none assignment=none cone_depth=none pattern=none");
 end else begin
 $display("R3E_ORACLE pass=0 signature=comparator_boundary first=cycle%0d topology=y",first);
 $display("R3E_WAVEFORM signal=y first_cycle=%0d cycle_offset=0 relation=same_cycle assignment=continuous cone_depth=1 pattern=boundary_value_mismatch",first);
 end
 $finish; end
 endmodule
