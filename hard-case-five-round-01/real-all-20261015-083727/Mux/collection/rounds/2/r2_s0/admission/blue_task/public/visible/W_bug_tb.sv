module tb;
integer sample_index=0, errors=0; reg [3:0] expected;


   reg [3:0] a;
   reg [3:0] b;
   reg [3:0] c;
   reg [3:0] d;
   wire [3:0] out;
   reg [1:0] sel;

   reg clk;
   reg instrumented_clk;

   integer i;
   
   always #5 clk = !clk;
   always #20 instrumented_clk = !instrumented_clk;

   mux_4to1_case  mux0 (   .a (a),
                           .b (b),
                           .c (c),
                           .d (d),
                           .sel (sel),
                           .out (out));


   integer f;

   initial begin
      $dumpfile("output_mux_4_1_tb.vcd");
      $dumpvars();
       f = $fopen("output_mux_4_1_tb.txt");
       $fwrite(f, "time,out[3],out[2],out[1],out[0]\n");
       forever begin
           @(posedge clk);
           case(sample_index)
0: expected=4'b0001;
1: expected=4'b0001;
2: expected=4'b0001;
3: expected=4'b0001;
4: expected=4'b0001;
5: expected=4'b0001;
6: expected=4'b0001;
7: expected=4'b0001;
8: expected=4'b0001;
9: expected=4'b0001;
10: expected=4'b0010;
11: expected=4'b0010;
12: expected=4'b0010;
13: expected=4'b0010;
14: expected=4'b0010;
15: expected=4'b0010;
16: expected=4'b0010;
17: expected=4'b0010;
18: expected=4'b0010;
19: expected=4'b0010;
20: expected=4'b0100;
21: expected=4'b0100;
22: expected=4'b0100;
23: expected=4'b0100;
24: expected=4'b0100;
25: expected=4'b0100;
26: expected=4'b0100;
27: expected=4'b0100;
28: expected=4'b0100;
29: expected=4'b0100;
30: expected=4'b1000;
31: expected=4'b1000;
32: expected=4'b1000;
33: expected=4'b1000;
34: expected=4'b1000;
35: expected=4'b1000;
36: expected=4'b1000;
37: expected=4'b1000;
38: expected=4'b1000;
39: expected=4'b1000;
40: expected=4'b1000;
41: expected=4'b1000;
42: expected=4'b1000;
43: expected=4'b1000;
44: expected=4'b1000;
45: expected=4'b1000;
46: expected=4'b1000;
47: expected=4'b1000;
48: expected=4'b1000;
49: expected=4'b1000;
50: expected=4'b0100;
51: expected=4'b0100;
52: expected=4'b0100;
53: expected=4'b0100;
54: expected=4'b0100;
55: expected=4'b0100;
56: expected=4'b0100;
57: expected=4'b0100;
58: expected=4'b0100;
59: expected=4'b0100;
60: expected=4'b0010;
61: expected=4'b0010;
62: expected=4'b0010;
63: expected=4'b0010;
64: expected=4'b0010;
65: expected=4'b0010;
66: expected=4'b0010;
67: expected=4'b0010;
68: expected=4'b0010;
69: expected=4'b0010;
70: expected=4'b0001;
71: expected=4'b0001;
72: expected=4'b0001;
73: expected=4'b0001;
74: expected=4'b0001;
75: expected=4'b0001;
76: expected=4'b0001;
77: expected=4'b0001;
78: expected=4'b0001;
79: expected=4'b0001;
80: expected=4'b0001;
81: expected=4'b0001;
82: expected=4'b0001;
83: expected=4'b0001;
84: expected=4'b0001;
85: expected=4'b0001;
86: expected=4'b0001;
87: expected=4'b0001;
88: expected=4'b0001;
89: expected=4'b0001;
90: expected=4'b0001;
91: expected=4'b0001;
92: expected=4'b0001;
93: expected=4'b0001;
94: expected=4'b0001;
95: expected=4'b0001;
96: expected=4'b0001;
97: expected=4'b0001;
98: expected=4'b0001;
99: expected=4'b0001;
100: expected=4'b0001;
101: expected=4'b0001;
102: expected=4'b0001;
103: expected=4'b0001;
104: expected=4'b0001;
105: expected=4'b0001;
106: expected=4'b0001;
107: expected=4'b0001;
108: expected=4'b0001;
109: expected=4'b0001;
110: expected=4'b0001;
111: expected=4'b0001;
112: expected=4'b0001;
113: expected=4'b0001;
114: expected=4'b0001;
115: expected=4'b0001;
116: expected=4'b0001;
117: expected=4'b0001;
118: expected=4'b0001;
119: expected=4'b0001;
120: expected=4'b0001;
121: expected=4'b0001;
122: expected=4'b0001;
123: expected=4'b0001;
124: expected=4'b0001;
125: expected=4'b0001;
126: expected=4'b0001;
127: expected=4'b0001;
128: expected=4'b0001;
129: expected=4'b0001;
130: expected=4'b0001;
131: expected=4'b0001;
132: expected=4'b0001;
133: expected=4'b0001;
134: expected=4'b0001;
135: expected=4'b0001;
136: expected=4'b0001;
137: expected=4'b0001;
138: expected=4'b0001;
139: expected=4'b0001;
140: expected=4'b0001;
141: expected=4'b0001;
142: expected=4'b0001;
143: expected=4'b0001;
144: expected=4'b0001;
145: expected=4'b0001;
146: expected=4'b0001;
147: expected=4'b0001;
148: expected=4'b0001;
149: expected=4'b0001;
default: begin $display("CHECK_FAIL excess oracle samples"); errors=errors+1; end
endcase
if ({out} !== expected) begin
 $display("CHECK_FAIL oracle sample=%0d got=%b expected=%b",sample_index,{out},expected);
 errors=errors+1;
end
sample_index=sample_index+1;
$fwrite(f, "%g,%b,%b,%b,%b\n", $time,out[3],out[2],out[1],out[0]);
       end
   end
   initial begin
      $monitor ("[%0t] sel=0x%0h a=0x%0h b=0x%0h c=0x%0h d=0x%0h out=0x%0h", $time, sel, a, b, c, d, out);

   	clk = 0;
      instrumented_clk = 0;

      sel <= 2'b00;
      a <= 4'b0001;
      b <= 4'b0010;
      c <= 4'b0100;
      d <= 4'b1000;

      #100;
      sel <= 2'b01;
      #100;
      sel <= 2'b10;
      #100;
      sel <= 2'b11;
      
      #100;

      sel <= 2'b00;
      d <= 4'b0001;
      c <= 4'b0010;
      b <= 4'b0100;
      a <= 4'b1000;

      #100;
      sel <= 2'b01;
      #100;
      sel <= 2'b10;
      #100;
      sel <= 2'b11;


      #800 $finish;
      #850 $fclose(f);
   end


final begin
 if(errors==0 && sample_index==150) $display("TESTBENCH PASS original oracle");
 else $display("CHECK_FAIL oracle errors=%0d samples=%0d",errors,sample_index);
end

endmodule