"""Small Icarus harness that dumps OISS outputs for Python validation."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .formats import read_actual
from .model import OISSError, Pattern, solve, validate_order


def write_bundle(patterns: list[Pattern], out: Path, *, force: bool = False) -> None:
    if out.exists() and any(out.iterdir()) and not force:
        raise OISSError(f"refusing to overwrite non-empty directory {out}; use --force")
    out.mkdir(parents=True, exist_ok=True)
    vectors = [f"{p.inst_latency_i:012X}{p.inst_seq_i:024X}" for p in patterns]
    (out / "vectors.mem").write_text("\n".join(vectors) + "\n", encoding="ascii")
    tb = f'''`timescale 1ns/1ps
module tb_oiss;
  localparam integer N = {len(patterns)};
  reg [143:0] vectors [0:N-1];
  reg [95:0] Inst_seq_I;
  reg [47:0] Inst_latency_I;
  wire [23:0] Inst_order_O;
  wire [8:0] Ex_cycle;
  integer fd, i;
  reg [1023:0] vectors_path, actual_path;
  OISS dut(.Inst_seq_I(Inst_seq_I), .Inst_latency_I(Inst_latency_I),
           .Inst_order_O(Inst_order_O), .Ex_cycle(Ex_cycle));
  initial begin
    if (!$value$plusargs("VECTORS=%s", vectors_path)) vectors_path = "vectors.mem";
    if (!$value$plusargs("ACTUAL=%s", actual_path)) actual_path = "actual.txt";
    $readmemh(vectors_path, vectors);
    fd = $fopen(actual_path, "w");
    if (!fd) $finish(2);
    for (i = 0; i < N; i = i + 1) begin
      {{Inst_latency_I, Inst_seq_I}} = vectors[i];
      #10;
      if ((^Ex_cycle === 1'bx) || (^Inst_order_O === 1'bx))
        $fwrite(fd, "x x\\n");
      else
        $fwrite(fd, "%0d %06x\\n", Ex_cycle, Inst_order_O);
    end
    $fclose(fd);
    $finish;
  end
endmodule
'''
    (out / "tb_oiss.sv").write_text(tb, encoding="ascii")
    (out / "manifest.json").write_text(json.dumps({"patterns": len(patterns)}, indent=2) + "\n")


def compare_actual(patterns: list[Pattern], goldens: list[int], actual_path: Path) -> dict:
    records = read_actual(actual_path, len(patterns))
    mismatches = []
    for index, (pattern, golden, (cycle, order)) in enumerate(zip(patterns, goldens, records)):
        try:
            validate_order(pattern, order, cycle, index, golden)
        except OISSError as exc:
            mismatches.append({"index": index, "golden_cycle": golden, "actual_cycle": cycle,
                               "actual_order": list(order), "reason": str(exc)})
    return {"passed": not mismatches, "patterns": len(patterns),
            "mismatch_count": len(mismatches), "mismatches": mismatches}


def run_iverilog(patterns: list[Pattern], goldens: list[int], dut_sources: list[Path], out: Path,
                 *, include_dirs: list[Path] | None = None, iverilog: str = "iverilog",
                 vvp: str = "vvp", force: bool = False) -> dict:
    if not dut_sources:
        raise OISSError("at least one DUT source is required")
    for source in dut_sources:
        if not source.is_file():
            raise OISSError(f"DUT source not found: {source}")
    include_dirs = include_dirs or []
    for directory in include_dirs:
        if not directory.is_dir():
            raise OISSError(f"include directory not found: {directory}")
    if shutil.which(iverilog) is None or shutil.which(vvp) is None:
        raise OISSError("Icarus requires both iverilog and vvp in PATH")
    write_bundle(patterns, out, force=force)
    executable = out / "sim.vvp"
    compile_command = [iverilog, "-g2012", "-s", "tb_oiss", "-o", str(executable)]
    for directory in include_dirs:
        compile_command.extend(("-I", str(directory)))
    compile_command.extend((str(out / "tb_oiss.sv"), *(str(path) for path in dut_sources)))
    compile_process = subprocess.run(
        compile_command, text=True, capture_output=True, check=False)
    (out / "compile.log").write_text(compile_process.stdout + compile_process.stderr)
    if compile_process.returncode:
        raise OISSError(f"iverilog compilation failed; see {out / 'compile.log'}")
    actual = out / "actual.txt"
    process = subprocess.run(
        [vvp, str(executable), f"+VECTORS={out / 'vectors.mem'}", f"+ACTUAL={actual}"],
        text=True, capture_output=True, check=False)
    (out / "sim.log").write_text(process.stdout + process.stderr)
    if process.returncode:
        raise OISSError(f"simulation failed; see {out / 'sim.log'}")
    report = compare_actual(patterns, goldens, actual)
    (out / "compare_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
