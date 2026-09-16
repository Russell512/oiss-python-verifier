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

First place the TA-provided 100-pattern files at:

```text
Real_Lab1/input.txt
Real_Lab1/output.txt
```

Then run the official 100 patterns from the repository root. These are the
default input, golden, DUT, and build paths:

```bash
python3 -m oiss run --force
```

Only after the official set passes, generate and run additional edge/random
patterns as documented in the main `README.md`.

If the design has submodules, list every source after `--dut`. Use repeated
`--include-dir` arguments for include files. Runtime `.mem`/`.hex` files must
also exist at the paths expected by the RTL.

Do not commit a course submission or third-party DUT unless you have permission.
