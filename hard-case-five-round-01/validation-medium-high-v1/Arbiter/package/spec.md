Four-agent synchronous arbitration FSM, preserving the original cycle contract.
Inputs: clock, active-high synchronous reset, req_0..req_3. Outputs: registered gnt_0..gnt_3.
IDLE chooses the lowest numbered asserted request. Each grant state holds while its own request remains asserted; otherwise it returns to IDLE.
On a rising edge, state takes the combinational next state. Registered grants use the pre-edge current state: IDLE clears all grants; a grant state asserts its own grant and otherwise holds existing grant registers. Reset clears state and all grants.
Combinational next-state evaluation must respond to changes of state as well as requests. Define defaults for unspecified states. Preserve interfaces, parameters, comments, and the original #1 delayed sequential assignments. The frozen public trace defines exact sample timing.
