#!/bin/bash
set -u -o pipefail

# run_case.py may invoke this script through a non-interactive shell that does
# not preload the ibex environment, so source it explicitly and keep a direct
# PATH fallback for Verilator.
if [ -f /etc/ibex_bash_env ]; then
  # shellcheck source=/dev/null
  source /etc/ibex_bash_env
fi
export PATH="/tools/verilator/current/bin:/tools/verilator/v4.210/bin:${PATH}"

cd /home/ibex

TEST_NAME="pmp_debug_dm_access"
TB_DIR="/home/ibex/.tb_${TEST_NAME}"
BUILD_LOG="${TB_DIR}/build.log"
SIM_LOG="${TB_DIR}/sim.log"

finish_test() {
  local status="$1"
  local rc="$2"

  echo "HWE_BENCH_RESULTS_START"
  echo "TEST: ${TEST_NAME} ... ${status}"
  echo "HWE_BENCH_RESULTS_END"
  exit "${rc}"
}

rm -rf "${TB_DIR}"
mkdir -p "${TB_DIR}"

cat > "${TB_DIR}/prim_stubs.sv" <<'EOF'
module prim_buf #(
  parameter int Width = 1
) (
  input  logic [Width-1:0] in_i,
  output logic [Width-1:0] out_o
);
  assign out_o = in_i;
endmodule

module prim_flop #(
  parameter int Width = 1,
  parameter logic [Width-1:0] ResetValue = '0
) (
  input  logic             clk_i,
  input  logic             rst_ni,
  input  logic [Width-1:0] d_i,
  output logic [Width-1:0] q_o
);
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      q_o <= ResetValue;
    end else begin
      q_o <= d_i;
    end
  end
endmodule

module prim_flop_en #(
  parameter int Width = 1,
  parameter logic [Width-1:0] ResetValue = '0
) (
  input  logic             clk_i,
  input  logic             rst_ni,
  input  logic             en_i,
  input  logic [Width-1:0] d_i,
  output logic [Width-1:0] q_o
);
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      q_o <= ResetValue;
    end else if (en_i) begin
      q_o <= d_i;
    end
  end
endmodule

module prim_clock_gating (
  input  logic clk_i,
  input  logic en_i,
  input  logic test_en_i,
  output logic clk_o
);
  logic unused_inputs;
  assign unused_inputs = en_i ^ test_en_i;
  assign clk_o = clk_i;
endmodule

module prim_clock_mux2 #(
  parameter bit NoFpgaBufG = 1'b1
) (
  input  logic clk0_i,
  input  logic clk1_i,
  input  logic sel_i,
  output logic clk_o
);
  logic unused_param;
  assign unused_param = NoFpgaBufG;
  assign clk_o = sel_i ? clk1_i : clk0_i;
endmodule

module prim_and2 (
  input  logic in0_i,
  input  logic in1_i,
  output logic out_o
);
  assign out_o = in0_i & in1_i;
endmodule

module prim_xor2 (
  input  logic in0_i,
  input  logic in1_i,
  output logic out_o
);
  assign out_o = in0_i ^ in1_i;
endmodule

module prim_xnor2 (
  input  logic in0_i,
  input  logic in1_i,
  output logic out_o
);
  assign out_o = ~(in0_i ^ in1_i);
endmodule

module prim_ram_1p import prim_ram_1p_pkg::*; #(
  parameter int Width = 32,
  parameter int Depth = 128,
  parameter int DataBitsPerMask = 1,
  parameter     MemInitFile = "",
  localparam int Aw = $clog2(Depth)
) (
  input  logic             clk_i,
  input  logic             req_i,
  input  logic             write_i,
  input  logic [Aw-1:0]    addr_i,
  input  logic [Width-1:0] wdata_i,
  input  logic [Width-1:0] wmask_i,
  output logic [Width-1:0] rdata_o,
  input  ram_1p_cfg_t      cfg_i
);
  logic unused_cfg;
  logic unused_mem_init;
  logic [Width-1:0] mem [Depth];

  assign unused_cfg = ^cfg_i;
  assign unused_mem_init = (MemInitFile != "");

  always_ff @(posedge clk_i) begin
    if (req_i) begin
      if (write_i) begin
        for (int i = 0; i < Width; i++) begin
          if (wmask_i[i]) begin
            mem[addr_i][i] <= wdata_i[i];
          end
        end
      end else begin
        rdata_o <= mem[addr_i];
      end
    end
  end
endmodule

package prim_count_pkg;
  typedef enum logic {
    CrossCnt,
    DupCnt
  } prim_count_style_e;

  typedef enum logic [1:0] {
    CmpInvalid = 2'b01,
    CmpValid   = 2'b10
  } cmp_valid_e;
endpackage

module prim_count import prim_count_pkg::*; #(
  parameter int Width = 2,
  parameter bit OutSelDnCnt = 1'b1,
  parameter prim_count_style_e CntStyle = CrossCnt,
  parameter bit EnableAlertTriggerSVA = 1'b1
) (
  input  logic             clk_i,
  input  logic             rst_ni,
  input  logic             clr_i,
  input  logic             set_i,
  input  logic [Width-1:0] set_cnt_i,
  input  logic             en_i,
  input  logic [Width-1:0] step_i,
  output logic [Width-1:0] cnt_o,
  output logic             err_o
);
  logic [Width-1:0] cnt_q;
  logic unused_cfg;

  assign unused_cfg = OutSelDnCnt ^ (CntStyle == DupCnt) ^ EnableAlertTriggerSVA;
  assign cnt_o = cnt_q;
  assign err_o = 1'b0;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cnt_q <= '0;
    end else if (clr_i) begin
      cnt_q <= '0;
    end else if (set_i) begin
      cnt_q <= set_cnt_i;
    end else if (en_i) begin
      cnt_q <= cnt_q + step_i;
    end
  end
endmodule
EOF

cat > "${TB_DIR}/tb_pmp_debug_dm.sv" <<'EOF'
module tb_pmp_debug_dm (
  input logic clk_i
);
  import ibex_pkg::*;

  localparam logic [31:0] BootAddr        = 32'h0000_0080;
  localparam logic [31:0] BootRegionTop   = 32'h0000_1000;
  localparam logic [31:0] DmBaseAddr      = 32'h1A11_0000;
  localparam logic [31:0] DmHaltAddr      = 32'h1A11_0800;
  localparam logic [31:0] DmExceptionAddr = 32'h1A11_0880;
  localparam logic [31:0] OutsideAddr     = 32'h0000_2000;
  localparam logic [11:0] DmDataOff       = 12'h100;
  localparam logic [11:0] DmStoreOff      = 12'h104;
  localparam logic [11:0] DmProgressOff   = 12'h108;
  localparam logic [11:0] DmResultOff     = 12'h10C;
  localparam logic [31:0] MagicValue      = 32'hCAFE_BEEF;

  localparam pmp_cfg_t PmpCfg[16] = '{
    '{lock: 1'b0, mode: PMP_MODE_TOR, exec: 1'b1, write: 1'b1, read: 1'b1},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0},
    '{lock: 1'b0, mode: PMP_MODE_OFF, exec: 1'b0, write: 1'b0, read: 1'b0}
  };
  localparam logic [33:0] PmpAddr[16] = '{
    34'h0000_1000,
    34'h0,
    34'h0,
    34'h0,
    34'h0,
    34'h0,
    34'h0,
    34'h0,
    34'h0,
    34'h0,
    34'h0,
    34'h0,
    34'h0,
    34'h0,
    34'h0,
    34'h0
  };
  localparam pmp_mseccfg_t PmpMseccfg = '{rlb: 1'b0, mmwp: 1'b1, mml: 1'b0};

  logic rst_ni;
  logic debug_req;

  logic instr_req;
  logic instr_gnt;
  logic instr_rvalid;
  logic [31:0] instr_addr;
  logic [31:0] instr_rdata;
  logic instr_err;

  logic data_req;
  logic data_gnt;
  logic data_rvalid;
  logic data_we;
  logic [3:0] data_be;
  logic [31:0] data_addr;
  logic [31:0] data_wdata;
  logic [31:0] data_rdata;
  logic data_err;

  logic dummy_instr_id;
  logic [4:0] rf_raddr_a;
  logic [4:0] rf_raddr_b;
  logic [4:0] rf_waddr_wb;
  logic rf_we_wb;
  logic [31:0] rf_wdata_wb;
  logic [31:0] rf_rdata_a;
  logic [31:0] rf_rdata_b;

  logic [IC_NUM_WAYS-1:0] ic_tag_req;
  logic ic_tag_write;
  logic [IC_INDEX_W-1:0] ic_tag_addr;
  logic [IC_TAG_SIZE-1:0] ic_tag_wdata;
  logic [IC_TAG_SIZE-1:0] ic_tag_rdata [IC_NUM_WAYS];
  logic [IC_NUM_WAYS-1:0] ic_data_req;
  logic ic_data_write;
  logic [IC_INDEX_W-1:0] ic_data_addr;
  logic [IC_LINE_SIZE-1:0] ic_data_wdata;
  logic [IC_LINE_SIZE-1:0] ic_data_rdata [IC_NUM_WAYS];

  logic irq_pending;
  crash_dump_t crash_dump;
  logic double_fault_seen;
  logic alert_minor;
  logic alert_major_internal;
  logic alert_major_bus;
  logic core_busy;

  logic [31:0] boot_imem [0:63];
  logic [31:0] dm_mem [0:1023];
  logic [31:0] rf_mem [0:31];
  logic [31:0] cycle_q;

  logic instr_rsp_valid_q;
  logic [31:0] instr_rsp_addr_q;

  logic data_rsp_valid_q;
  logic [31:0] data_rsp_addr_q;
  logic data_rsp_we_q;
  logic [3:0] data_rsp_be_q;
  logic [31:0] data_rsp_wdata_q;

  function automatic logic [31:0] enc_lui(
    input logic [4:0] rd,
    input logic [19:0] imm20
  );
    enc_lui = {imm20, rd, 7'b0110111};
  endfunction

  function automatic logic [31:0] enc_addi(
    input logic [4:0] rd,
    input logic [4:0] rs1,
    input integer imm
  );
    logic signed [11:0] simm;
    begin
      simm = imm[11:0];
      enc_addi = {simm[11:0], rs1, 3'b000, rd, 7'b0010011};
    end
  endfunction

  function automatic logic [31:0] enc_lw(
    input logic [4:0] rd,
    input logic [4:0] rs1,
    input integer imm
  );
    logic signed [11:0] simm;
    begin
      simm = imm[11:0];
      enc_lw = {simm[11:0], rs1, 3'b010, rd, 7'b0000011};
    end
  endfunction

  function automatic logic [31:0] enc_sw(
    input logic [4:0] rs2,
    input logic [4:0] rs1,
    input integer imm
  );
    logic signed [11:0] simm;
    begin
      simm = imm[11:0];
      enc_sw = {simm[11:5], rs2, rs1, 3'b010, simm[4:0], 7'b0100011};
    end
  endfunction

  function automatic logic [31:0] enc_jal(
    input logic [4:0] rd,
    input integer imm
  );
    logic signed [20:0] simm;
    begin
      simm = imm[20:0];
      enc_jal = {simm[20], simm[10:1], simm[11], simm[19:12], rd, 7'b1101111};
    end
  endfunction

  function automatic logic dm_addr_valid(input logic [31:0] addr);
    dm_addr_valid = ((addr & 32'hFFFF_F000) == DmBaseAddr);
  endfunction

  function automatic int dm_word_idx(input logic [31:0] addr);
    dm_word_idx = (addr - DmBaseAddr) >> 2;
  endfunction

  function automatic logic [31:0] instr_mem_word(input logic [31:0] addr);
    if ((addr >= BootAddr) && (addr < BootAddr + 32'd256)) begin
      instr_mem_word = boot_imem[(addr - BootAddr) >> 2];
    end else if (dm_addr_valid(addr)) begin
      instr_mem_word = dm_mem[dm_word_idx(addr)];
    end else begin
      instr_mem_word = 32'h0000_0013;
    end
  endfunction

  assign rst_ni = (cycle_q >= 32'd5);
  assign debug_req = (cycle_q >= 32'd20) && (cycle_q < 32'd24);

  assign instr_gnt = instr_req;
  assign instr_rvalid = instr_rsp_valid_q;
  assign instr_rdata = instr_mem_word(instr_rsp_addr_q);
  assign instr_err = 1'b0;

  assign data_gnt = data_req;
  assign data_rvalid = data_rsp_valid_q;
  assign data_err = 1'b0;

  always_comb begin
    if (data_rsp_we_q) begin
      data_rdata = 32'h0000_0000;
    end else if (dm_addr_valid(data_rsp_addr_q)) begin
      data_rdata = dm_mem[dm_word_idx(data_rsp_addr_q)];
    end else begin
      data_rdata = 32'h0000_0000;
    end
  end

  always_comb begin
    rf_rdata_a = (rf_raddr_a == 5'd0) ? 32'h0000_0000 : rf_mem[rf_raddr_a];
    rf_rdata_b = (rf_raddr_b == 5'd0) ? 32'h0000_0000 : rf_mem[rf_raddr_b];
  end

  always_ff @(posedge clk_i) begin
    cycle_q <= cycle_q + 32'd1;

    if (!rst_ni) begin
      instr_rsp_valid_q <= 1'b0;
      instr_rsp_addr_q <= 32'h0;
      data_rsp_valid_q <= 1'b0;
      data_rsp_addr_q <= 32'h0;
      data_rsp_we_q <= 1'b0;
      data_rsp_be_q <= 4'h0;
      data_rsp_wdata_q <= 32'h0;
      for (int i = 0; i < 32; i++) begin
        rf_mem[i] <= 32'h0;
      end
    end else begin
      instr_rsp_valid_q <= instr_req;
      if (instr_req) begin
        instr_rsp_addr_q <= instr_addr;
      end

      data_rsp_valid_q <= data_req;
      if (data_req) begin
        data_rsp_addr_q <= data_addr;
        data_rsp_we_q <= data_we;
        data_rsp_be_q <= data_be;
        data_rsp_wdata_q <= data_wdata;
      end

      if (rf_we_wb && (rf_waddr_wb != 5'd0)) begin
        rf_mem[rf_waddr_wb] <= rf_wdata_wb;
      end

      if (data_rsp_valid_q && data_rsp_we_q && dm_addr_valid(data_rsp_addr_q)) begin
        for (int i = 0; i < 4; i++) begin
          if (data_rsp_be_q[i]) begin
            dm_mem[dm_word_idx(data_rsp_addr_q)][8*i +: 8] <= data_rsp_wdata_q[8*i +: 8];
          end
        end
      end

      if ((dm_mem[dm_word_idx(DmBaseAddr + DmResultOff)] == 32'd1) &&
          (dm_mem[dm_word_idx(DmBaseAddr + DmStoreOff)] == MagicValue)) begin
        $display("TB_PASS result=%0d store=%08x cycle=%0d",
                 dm_mem[dm_word_idx(DmBaseAddr + DmResultOff)],
                 dm_mem[dm_word_idx(DmBaseAddr + DmStoreOff)],
                 cycle_q);
        $finish;
      end

      if (dm_mem[dm_word_idx(DmBaseAddr + DmResultOff)] == 32'd2) begin
        $fatal(1, "TB_FAIL outside access unexpectedly succeeded cycle=%0d", cycle_q);
      end

      if (cycle_q > 32'd500) begin
        $fatal(1, "TB_FAIL timeout result=%0d progress=%0d store=%08x cycle=%0d",
               dm_mem[dm_word_idx(DmBaseAddr + DmResultOff)],
               dm_mem[dm_word_idx(DmBaseAddr + DmProgressOff)],
               dm_mem[dm_word_idx(DmBaseAddr + DmStoreOff)],
               cycle_q);
      end
    end
  end

  initial begin
    cycle_q = 32'd0;
    instr_rsp_valid_q = 1'b0;
    instr_rsp_addr_q = 32'h0;
    data_rsp_valid_q = 1'b0;
    data_rsp_addr_q = 32'h0;
    data_rsp_we_q = 1'b0;
    data_rsp_be_q = 4'h0;
    data_rsp_wdata_q = 32'h0;

    for (int i = 0; i < 64; i++) begin
      boot_imem[i] = 32'h0000_0013;
    end

    for (int i = 0; i < 1024; i++) begin
      dm_mem[i] = 32'h0000_0013;
    end

    // Keep the core alive in an allowed boot region until debug_req_i arrives.
    boot_imem[0] = enc_jal(5'd0, 0);

    // Debug ROM program: successful DM fetch/load/store must happen before the
    // outside access faults. The exception handler mirrors the progress marker
    // into the result word so the host can distinguish a DM fault from the
    // expected outside-DM fault.
    dm_mem[dm_word_idx(DmHaltAddr + 32'd0)]  = enc_lui(5'd1, DmBaseAddr[31:12]);
    dm_mem[dm_word_idx(DmHaltAddr + 32'd4)]  = enc_lw(5'd2, 5'd1, DmDataOff);
    dm_mem[dm_word_idx(DmHaltAddr + 32'd8)]  = enc_sw(5'd2, 5'd1, DmStoreOff);
    dm_mem[dm_word_idx(DmHaltAddr + 32'd12)] = enc_addi(5'd3, 5'd0, 1);
    dm_mem[dm_word_idx(DmHaltAddr + 32'd16)] = enc_sw(5'd3, 5'd1, DmProgressOff);
    dm_mem[dm_word_idx(DmHaltAddr + 32'd20)] = enc_lui(5'd4, OutsideAddr[31:12]);
    dm_mem[dm_word_idx(DmHaltAddr + 32'd24)] = enc_lw(5'd5, 5'd4, 0);
    dm_mem[dm_word_idx(DmHaltAddr + 32'd28)] = enc_addi(5'd6, 5'd0, 2);
    dm_mem[dm_word_idx(DmHaltAddr + 32'd32)] = enc_sw(5'd6, 5'd1, DmResultOff);
    dm_mem[dm_word_idx(DmHaltAddr + 32'd36)] = enc_jal(5'd0, 0);

    dm_mem[dm_word_idx(DmExceptionAddr + 32'd0)]  = enc_lui(5'd1, DmBaseAddr[31:12]);
    dm_mem[dm_word_idx(DmExceptionAddr + 32'd4)]  = enc_lw(5'd2, 5'd1, DmProgressOff);
    dm_mem[dm_word_idx(DmExceptionAddr + 32'd8)]  = enc_sw(5'd2, 5'd1, DmResultOff);
    dm_mem[dm_word_idx(DmExceptionAddr + 32'd12)] = enc_jal(5'd0, 0);

    dm_mem[dm_word_idx(DmBaseAddr + DmDataOff)] = MagicValue;
    dm_mem[dm_word_idx(DmBaseAddr + DmStoreOff)] = 32'h0;
    dm_mem[dm_word_idx(DmBaseAddr + DmProgressOff)] = 32'h0;
    dm_mem[dm_word_idx(DmBaseAddr + DmResultOff)] = 32'h0;

    for (int i = 0; i < IC_NUM_WAYS; i++) begin
      ic_tag_rdata[i] = '0;
      ic_data_rdata[i] = '0;
    end
  end

  ibex_core #(
    .SecureIbex       (1'b0),
    .RegFileECC       (1'b0),
    .RegFileDataWidth (32),
    .DummyInstructions(1'b0),
    .ResetAll         (1'b0),
    .MemECC           (1'b0),
    .MemDataWidth     (32),
    .ICache           (1'b0),
    .ICacheECC        (1'b0),
    .PMPEnable        (1'b1),
    .PMPNumRegions    (1),
    .PMPRstCfg        (PmpCfg),
    .PMPRstAddr       (PmpAddr),
    .PMPRstMsecCfg    (PmpMseccfg),
    .BranchPredictor  (1'b0),
    .WritebackStage   (1'b0),
    .DmHaltAddr       (DmHaltAddr),
    .DmExceptionAddr  (DmExceptionAddr)
  ) dut (
    .clk_i               (clk_i),
    .rst_ni              (rst_ni),
    .hart_id_i           (32'h0),
    .boot_addr_i         (BootAddr),
    .instr_req_o         (instr_req),
    .instr_gnt_i         (instr_gnt),
    .instr_rvalid_i      (instr_rvalid),
    .instr_addr_o        (instr_addr),
    .instr_rdata_i       (instr_rdata),
    .instr_err_i         (instr_err),
    .data_req_o          (data_req),
    .data_gnt_i          (data_gnt),
    .data_rvalid_i       (data_rvalid),
    .data_we_o           (data_we),
    .data_be_o           (data_be),
    .data_addr_o         (data_addr),
    .data_wdata_o        (data_wdata),
    .data_rdata_i        (data_rdata),
    .data_err_i          (data_err),
    .dummy_instr_id_o    (dummy_instr_id),
    .rf_raddr_a_o        (rf_raddr_a),
    .rf_raddr_b_o        (rf_raddr_b),
    .rf_waddr_wb_o       (rf_waddr_wb),
    .rf_we_wb_o          (rf_we_wb),
    .rf_wdata_wb_ecc_o   (rf_wdata_wb),
    .rf_rdata_a_ecc_i    (rf_rdata_a),
    .rf_rdata_b_ecc_i    (rf_rdata_b),
    .ic_tag_req_o        (ic_tag_req),
    .ic_tag_write_o      (ic_tag_write),
    .ic_tag_addr_o       (ic_tag_addr),
    .ic_tag_wdata_o      (ic_tag_wdata),
    .ic_tag_rdata_i      (ic_tag_rdata),
    .ic_data_req_o       (ic_data_req),
    .ic_data_write_o     (ic_data_write),
    .ic_data_addr_o      (ic_data_addr),
    .ic_data_wdata_o     (ic_data_wdata),
    .ic_data_rdata_i     (ic_data_rdata),
    .ic_scr_key_valid_i  (1'b0),
    .irq_software_i      (1'b0),
    .irq_timer_i         (1'b0),
    .irq_external_i      (1'b0),
    .irq_fast_i          ('0),
    .irq_nm_i            (1'b0),
    .irq_pending_o       (irq_pending),
    .debug_req_i         (debug_req),
    .crash_dump_o        (crash_dump),
    .double_fault_seen_o (double_fault_seen),
    .fetch_enable_i      (IbexMuBiOn),
    .alert_minor_o       (alert_minor),
    .alert_major_internal_o(alert_major_internal),
    .alert_major_bus_o   (alert_major_bus),
    .core_busy_o         (core_busy)
  );

endmodule
EOF

cat > "${TB_DIR}/sim_main.cpp" <<'EOF'
#include "Vtb_pmp_debug_dm.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>

namespace {

void tick(Vtb_pmp_debug_dm* top) {
  top->clk_i = 0;
  top->eval();
  top->clk_i = 1;
  top->eval();
}

}  // namespace

double sc_time_stamp() {
  return 0.0;
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);

  auto* top = new Vtb_pmp_debug_dm;
  std::uint64_t cycles = 0;

  while (!Verilated::gotFinish() && cycles < 4000) {
    tick(top);
    ++cycles;
  }

  if (!Verilated::gotFinish()) {
    std::fprintf(stderr, "TB_FAIL host timeout cycles=%llu\n",
                 static_cast<unsigned long long>(cycles));
    delete top;
    return 1;
  }

  delete top;
  return 0;
}
EOF

set +e
timeout 1200 verilator --cc --exe --build --top-module tb_pmp_debug_dm \
  -DSYNTHESIS -DDV_FCOV_DISABLE -Wno-fatal \
  -Irtl \
  -Ivendor/lowrisc_ip/ip/prim/rtl \
  -Ivendor/lowrisc_ip/dv/sv/dv_utils \
  -Mdir "${TB_DIR}/obj_dir" \
  vendor/lowrisc_ip/ip/prim/rtl/prim_util_pkg.sv \
  vendor/lowrisc_ip/ip/prim/rtl/prim_cipher_pkg.sv \
  vendor/lowrisc_ip/ip/prim/rtl/prim_mubi_pkg.sv \
  vendor/lowrisc_ip/ip/prim/rtl/prim_secded_pkg.sv \
  vendor/lowrisc_ip/ip/prim/rtl/prim_ram_1p_pkg.sv \
  "${TB_DIR}/prim_stubs.sv" \
  vendor/lowrisc_ip/ip/prim/rtl/prim_lfsr.sv \
  vendor/lowrisc_ip/ip/prim/rtl/prim_clock_gating_sync.sv \
  rtl/ibex_pkg.sv \
  rtl/ibex_alu.sv \
  rtl/ibex_branch_predict.sv \
  rtl/ibex_compressed_decoder.sv \
  rtl/ibex_controller.sv \
  rtl/ibex_cs_registers.sv \
  rtl/ibex_csr.sv \
  rtl/ibex_counter.sv \
  rtl/ibex_decoder.sv \
  rtl/ibex_ex_block.sv \
  rtl/ibex_fetch_fifo.sv \
  rtl/ibex_id_stage.sv \
  rtl/ibex_if_stage.sv \
  rtl/ibex_load_store_unit.sv \
  rtl/ibex_multdiv_fast.sv \
  rtl/ibex_multdiv_slow.sv \
  rtl/ibex_prefetch_buffer.sv \
  rtl/ibex_pmp.sv \
  rtl/ibex_wb_stage.sv \
  rtl/ibex_dummy_instr.sv \
  rtl/ibex_core.sv \
  "${TB_DIR}/tb_pmp_debug_dm.sv" \
  "${TB_DIR}/sim_main.cpp" > "${BUILD_LOG}" 2>&1
build_rc=$?

if [ "${build_rc}" -ne 0 ]; then
  tail -n 80 "${BUILD_LOG}"
  finish_test "FAIL" 1
fi

SIM_BIN="${TB_DIR}/obj_dir/Vtb_pmp_debug_dm"
if [ ! -x "${SIM_BIN}" ]; then
  echo "Simulation binary not found at ${SIM_BIN}"
  finish_test "FAIL" 1
fi

timeout 1200 "${SIM_BIN}" > "${SIM_LOG}" 2>&1
sim_rc=$?
cat "${SIM_LOG}"

if [ "${sim_rc}" -eq 0 ]; then
  finish_test "PASS" 0
fi

finish_test "FAIL" 1
