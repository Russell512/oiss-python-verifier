from __future__ import annotations

import tempfile
import unittest
from itertools import permutations
from pathlib import Path

from oiss import (Instruction, Pattern, dependency_structure, read_golden, read_input,
                  schedule_order, solve, validate_order)
from oiss.generate import generate_cases, write_generated
from oiss.model import LEGAL_LATENCIES, OISSError

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_INPUT = ROOT / "Real_Lab1" / "input.txt"
OFFICIAL_OUTPUT = ROOT / "Real_Lab1" / "output.txt"


def inst(op: int, rs: int, rt: int, rd: int) -> Instruction:
    return Instruction((op << 9) | (rs << 6) | (rt << 3) | rd)


class OISSModelTests(unittest.TestCase):
    def test_read_write_sets_match_pattern_v(self):
        self.assertEqual((inst(0, 2, 3, 1).read_mask, inst(0, 2, 3, 1).write_mask),
                         ((1 << 2) | (1 << 3), 1 << 1))
        self.assertEqual((inst(4, 2, 3, 1).read_mask, inst(4, 2, 3, 1).write_mask),
                         (0, 1 << 1))
        self.assertEqual((inst(5, 2, 3, 1).read_mask, inst(5, 2, 3, 1).write_mask),
                         (1 << 1, 0))
        self.assertEqual((inst(6, 2, 3, 1).read_mask, inst(6, 2, 3, 1).write_mask),
                         ((1 << 2) | (1 << 3), 0))
        self.assertEqual((inst(7, 2, 3, 1).read_mask, inst(7, 2, 3, 1).write_mask), (0, 0))

    def test_pdf_example_is_41_cycles(self):
        instructions = (
            inst(2, 2, 3, 1), inst(3, 6, 7, 5), inst(4, 2, 2, 0), inst(6, 6, 7, 2),
            inst(0, 1, 4, 1), inst(7, 0, 0, 1), inst(5, 1, 1, 4), inst(5, 5, 2, 1),
        )
        pattern = Pattern(instructions, (3, 1, 30, 40, 8, 7, 3, 1))
        shown = schedule_order(pattern, (0, 1, 2, 3, 6, 5, 4, 7))
        self.assertEqual(shown.cycle, 41)
        self.assertEqual(solve(pattern).cycle, 41)

    def test_dependency_order_and_strict_issue_stall(self):
        instructions = (inst(2, 2, 3, 1), inst(0, 1, 4, 1)) + tuple(inst(7, 0, 0, i) for i in range(6))
        pattern = Pattern(instructions, (3, 1, 30, 40, 8, 7, 3, 1))
        with self.assertRaises(OISSError):
            schedule_order(pattern, (1, 0, 2, 3, 4, 5, 6, 7))
        stalled = schedule_order(pattern, (0, 1, 2, 3, 4, 5, 6, 7))
        self.assertEqual(stalled.starts[1], 30)
        self.assertEqual(stalled.starts[2], 31)

    def test_bit_packing_lsb_fields(self):
        instructions = tuple(Instruction(i) for i in range(8))
        pattern = Pattern(instructions, (1, 1, 20, 30, 6, 6, 2, 1))
        self.assertEqual(pattern.inst_seq_i & 0xFFF, 0)
        self.assertEqual((pattern.inst_seq_i >> 84) & 0xFFF, 7)
        self.assertEqual(pattern.inst_latency_i & 0x3F, 1)
        self.assertEqual((pattern.inst_latency_i >> 42) & 0x3F, 1)

    @unittest.skipUnless(OFFICIAL_INPUT.is_file() and OFFICIAL_OUTPUT.is_file(),
                         "TA open-pattern files are not distributed in the public repository")
    def test_all_supplied_goldens_and_orders(self):
        patterns = read_input(OFFICIAL_INPUT)
        goldens = read_golden(OFFICIAL_OUTPUT, len(patterns))
        self.assertEqual(len(patterns), 100)
        for index, (pattern, golden) in enumerate(zip(patterns, goldens)):
            result = solve(pattern)
            self.assertEqual(result.cycle, golden, index)
            validate_order(pattern, result.order, result.cycle, index, golden)

    def test_input_rejects_wrong_token_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.txt"
            path.write_text("1\n000\n", encoding="ascii")
            with self.assertRaises(OISSError):
                read_input(path)

    def test_generator_reproducibility_coverage_and_roundtrip(self):
        first = generate_cases(18, seed=260916)
        second = generate_cases(18, seed=260916)
        different = generate_cases(18, seed=260917)
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertEqual({dependency_structure(pattern) for pattern in first},
                         {"none", "one-chain", "two-chains"})
        self.assertEqual({instruction.opcode for pattern in first
                          for instruction in pattern.instructions}, set(range(8)))
        for pattern in first:
            addresses = [instruction.word >> 3 & 0x3F for instruction in pattern.instructions
                         if instruction.opcode in (4, 5)]
            self.assertEqual(len(addresses), len(set(addresses)))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "generated"
            manifest = write_generated(first, out, 260916)
            restored = read_input(out / "input.txt")
            goldens = read_golden(out / "output.txt", len(restored))
            self.assertEqual(restored, first)
            self.assertEqual(manifest["patterns"], 18)
            self.assertTrue(all(solve(pattern).cycle == golden
                                for pattern, golden in zip(restored, goldens)))

    def test_generator_hits_latency_minimum_and_maximum(self):
        patterns = generate_cases(4, seed=1)
        self.assertEqual(patterns[0].latencies, tuple(low for low, _ in LEGAL_LATENCIES))
        self.assertEqual(patterns[1].latencies, tuple(high for _, high in LEGAL_LATENCIES))
        for pattern in patterns:
            for value, (low, high) in zip(pattern.latencies, LEGAL_LATENCIES):
                self.assertLessEqual(low, value)
                self.assertLessEqual(value, high)

    def test_no_dependency_fast_path_matches_exhaustive_search(self):
        pattern = generate_cases(1, seed=7)[0]
        self.assertEqual(dependency_structure(pattern), "none")
        exhaustive = min(schedule_order(pattern, order).cycle
                         for order in permutations(range(8)))
        self.assertEqual(solve(pattern).cycle, exhaustive)

    def test_generator_rejects_invalid_count_and_overwrite(self):
        for count in (0, -1, True):
            with self.assertRaises(OISSError):
                generate_cases(count)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "generated"
            patterns = generate_cases(3)
            write_generated(patterns, out, 42)
            with self.assertRaises(OISSError):
                write_generated(patterns, out, 42)
            write_generated(patterns, out, 42, force=True)


if __name__ == "__main__":
    unittest.main()
