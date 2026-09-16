# Put your RTL here

For a single-file design, copy your top module to:

```text
dut/OISS.v
```

The required top-level interface is:

```verilog
module OISS (
    input  [95:0] Inst_seq_I,
    input  [47:0] Inst_latency_I,
    output [23:0] Inst_order_O,
    output [8:0]  Ex_cycle
);
```

Then run from the repository root:

```bash
python3 -m oiss run \
  --dut dut/OISS.v \
  --input build/oiss_random_1000/input.txt \
  --golden build/oiss_random_1000/output.txt \
  --build build/oiss_random_1000/simulation \
  --force
```

If the design has submodules, list every source after `--dut`. Use repeated
`--include-dir` arguments for include files. Runtime `.mem`/`.hex` files must
also exist at the paths expected by the RTL.

Do not commit a course submission or third-party DUT unless you have permission.
