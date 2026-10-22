#!/bin/bash
cd /home/ibex

TEST_NAME="prefetch_buffer_early_request"
WORKDIR="/home/ibex/.msb/${TEST_NAME}"

set +e
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"

cat > "$WORKDIR/sim_main.cpp" <<'EOF'
#include "Vibex_prefetch_buffer.h"
#include "verilated.h"

#include <cstdint>
#include <iostream>
#include <string>

namespace {

struct PendingResp {
  bool valid;
  uint32_t addr;
};

uint32_t MemWord(uint32_t addr) {
  switch (addr) {
    case 0x00000000:
      return 0x00030001;
    case 0x00000004:
      return 0x22231111;
    case 0x00000008:
      return 0x44443333;
    default:
      return 0x00010001;
  }
}

void SetMemoryInputs(Vibex_prefetch_buffer &top, const PendingResp &pending) {
  top.instr_rvalid_i = pending.valid ? 1 : 0;
  top.instr_rdata_i = MemWord(pending.addr);
  top.instr_err_i = 0;
  top.instr_pmp_err_i = 0;
}

void TraceState(const Vibex_prefetch_buffer &top,
                const std::string &step_name,
                int cycle,
                const PendingResp &pending) {
  std::cout << "TRACE cycle=" << cycle
            << " step=" << step_name
            << " req=" << static_cast<int>(top.req_i)
            << " ready=" << static_cast<int>(top.ready_i)
            << " branch=" << static_cast<int>(top.branch_i)
            << " pending_valid=" << static_cast<int>(pending.valid)
            << " pending_addr=0x" << std::hex << pending.addr
            << " valid_o=" << static_cast<int>(top.valid_o)
            << " addr_o=0x" << top.addr_o
            << " instr_req_o=" << static_cast<int>(top.instr_req_o)
            << " instr_addr_o=0x" << top.instr_addr_o
            << " busy_o=" << static_cast<int>(top.busy_o)
            << std::dec << '\n';
}

bool StepCycle(Vibex_prefetch_buffer &top,
               PendingResp &pending,
               bool req,
               bool ready,
               bool branch,
               int &cycle,
               const std::string &step_name,
               const bool check_early_request,
               const bool check_no_bubble) {
  top.req_i = req ? 1 : 0;
  top.ready_i = ready ? 1 : 0;
  top.branch_i = branch ? 1 : 0;
  top.branch_spec_i = branch ? 1 : 0;
  top.addr_i = 0;

  top.clk_i = 0;
  SetMemoryInputs(top, pending);
  top.instr_gnt_i = 0;
  top.eval();

  top.instr_gnt_i = top.instr_req_o;
  top.eval();

  TraceState(top, step_name, cycle, pending);

  if (check_early_request) {
    if (!(top.instr_req_o && top.instr_addr_o == 0x00000008)) {
      std::cerr << "CHECK_FAIL expected immediate refill request for address 0x8"
                << '\n';
      return false;
    }
  }

  if (check_no_bubble) {
    if (!(top.valid_o && top.addr_o == 0x00000006)) {
      std::cerr << "CHECK_FAIL expected next unaligned instruction at address 0x6 without a bubble"
                << '\n';
      return false;
    }
  }

  PendingResp next_pending{top.instr_req_o != 0,
                           static_cast<uint32_t>(top.instr_addr_o)};

  top.clk_i = 1;
  top.eval();

  pending = next_pending;
  ++cycle;
  return true;
}

void TickReset(Vibex_prefetch_buffer &top, PendingResp &pending, int &cycle) {
  top.req_i = 0;
  top.ready_i = 0;
  top.branch_i = 0;
  top.branch_spec_i = 0;
  top.addr_i = 0;
  top.clk_i = 0;
  SetMemoryInputs(top, pending);
  top.instr_gnt_i = 0;
  top.eval();
  top.clk_i = 1;
  top.eval();
  ++cycle;
}

}  // namespace

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  Verilated::traceEverOn(false);

  Vibex_prefetch_buffer top;
  PendingResp pending{false, 0};
  int cycle = 0;

  top.rst_ni = 0;
  TickReset(top, pending, cycle);
  TickReset(top, pending, cycle);
  top.rst_ni = 1;

  if (!StepCycle(top, pending, false, false, true, cycle, "branch_init", false, false)) return 1;
  if (!StepCycle(top, pending, true, false, false, cycle, "fetch_word0", false, false)) return 1;
  if (!StepCycle(top, pending, true, false, false, cycle, "fetch_word1", false, false)) return 1;
  if (!StepCycle(top, pending, false, false, false, cycle, "drain_outstanding", false, false)) return 1;
  if (!StepCycle(top, pending, true, false, false, cycle, "check_early_refill", true, false)) return 1;
  if (!StepCycle(top, pending, true, true, false, cycle, "consume_compressed", false, false)) return 1;
  if (!StepCycle(top, pending, true, true, false, cycle, "consume_unaligned32", false, false)) return 1;
  if (!StepCycle(top, pending, true, false, false, cycle, "check_no_fetch_bubble", false, true)) return 1;

  std::cout << "TESTBENCH PASS" << '\n';
  top.final();
  return 0;
}
EOF

timeout 1200s verilator --cc --exe --build --top-module ibex_prefetch_buffer \
  -Wno-fatal -Wno-DECLFILENAME \
  -Mdir "$WORKDIR/obj_dir" \
  -Ivendor/lowrisc_ip/prim/rtl \
  rtl/ibex_fetch_fifo.sv rtl/ibex_prefetch_buffer.sv \
  "$WORKDIR/sim_main.cpp"
build_rc=$?

echo "HWE_BENCH_RESULTS_START"

if [ $build_rc -ne 0 ]; then
  echo "TEST: ${TEST_NAME} ... FAIL"
  echo "HWE_BENCH_RESULTS_END"
  exit $build_rc
fi

timeout 1200s "$WORKDIR/obj_dir/Vibex_prefetch_buffer"
run_rc=$?

if [ $run_rc -eq 0 ]; then
  echo "TEST: ${TEST_NAME} ... PASS"
else
  echo "TEST: ${TEST_NAME} ... FAIL"
fi

echo "HWE_BENCH_RESULTS_END"

exit $run_rc
