"""CLI for solving and checking the Real_Lab1 OISS assignment."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .formats import read_golden, read_input
from .generate import generate_cases, write_generated
from .hdl import run_iverilog
from .model import OISSError, solve, validate_order


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="OISS Python golden/reference verifier")
    commands = root.add_subparsers(dest="command", required=True)
    item = commands.add_parser("generate", help="create TA-format edge/random patterns and goldens")
    item.add_argument("--count", type=int, default=1000)
    item.add_argument("--seed", type=int, default=42)
    item.add_argument("--out", type=Path, default=Path("build/oiss_random"))
    item.add_argument("--force", action="store_true")
    for name in ("verify", "solve"):
        item = commands.add_parser(name)
        item.add_argument("--input", type=Path, default=Path("Real_Lab1/input.txt"))
        if name == "verify":
            item.add_argument("--golden", type=Path, default=Path("Real_Lab1/output.txt"))
            item.add_argument("--report", type=Path)
        else:
            item.add_argument("--output", type=Path)
    item = commands.add_parser("run", help="compile an OISS.v, dump outputs, and validate them")
    item.add_argument("--dut", type=Path, nargs="+", default=[Path("dut/OISS.v")],
                      help="one or more Verilog/SystemVerilog source files")
    item.add_argument("--include-dir", type=Path, action="append", default=[],
                      help="Verilog include directory; repeat for multiple directories")
    item.add_argument("--input", type=Path, default=Path("Real_Lab1/input.txt"))
    item.add_argument("--golden", type=Path, default=Path("Real_Lab1/output.txt"))
    item.add_argument("--build", type=Path, default=Path("build/oiss"))
    item.add_argument("--iverilog", default="iverilog")
    item.add_argument("--vvp", default="vvp")
    item.add_argument("--force", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "generate":
            patterns = generate_cases(args.count, args.seed)
            manifest = write_generated(patterns, args.out, args.seed, force=args.force)
            structures = ", ".join(
                f"{name}={count}" for name, count in manifest["dependency_structures"].items())
            print(f"Generated {len(patterns)} patterns in {args.out.resolve()}")
            print(f"Dependency structures: {structures}")
            return 0
        patterns = read_input(args.input)
        if args.command == "solve":
            lines = []
            for pattern in patterns:
                result = solve(pattern)
                lines.append(f"{result.cycle} " + " ".join(map(str, result.order)))
            text = "\n".join(lines) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text, encoding="ascii")
            else:
                print(text, end="")
            return 0

        goldens = read_golden(args.golden, len(patterns))
        if args.command == "run":
            report = run_iverilog(patterns, goldens, args.dut, args.build,
                                  include_dirs=args.include_dir,
                                  iverilog=args.iverilog, vvp=args.vvp, force=args.force)
            print(f"{'PASS' if report['passed'] else 'MISMATCH'}: "
                  f"{report['patterns'] - report['mismatch_count']}/{report['patterns']} patterns")
            return 0 if report["passed"] else 1

        mismatches = []
        solutions = []
        for index, (pattern, golden) in enumerate(zip(patterns, goldens)):
            result = solve(pattern)
            validate_order(pattern, result.order, result.cycle, index, result.cycle)
            solutions.append({"index": index, "golden": golden, "calculated": result.cycle,
                              "order": list(result.order), "packed_order_hex": f"{result.packed_order:06X}"})
            if result.cycle != golden:
                mismatches.append(solutions[-1])
        report = {"passed": not mismatches, "patterns": len(patterns),
                  "mismatch_count": len(mismatches), "mismatches": mismatches,
                  "solutions": solutions}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"{'PASS' if report['passed'] else 'MISMATCH'}: "
              f"{len(patterns) - len(mismatches)}/{len(patterns)} supplied minimum cycles")
        for item in mismatches:
            print(f"  index={item['index']} file={item['golden']} model={item['calculated']}")
        return 0 if report["passed"] else 1
    except (OISSError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
