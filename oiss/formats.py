"""Readers for the exact Real_Lab1 input.txt and output.txt formats."""
from __future__ import annotations

from pathlib import Path
from .model import Instruction, OISSError, Pattern


def _tokens(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8-sig").split()
    except OSError as exc:
        raise OISSError(f"cannot read {path}: {exc}") from exc


def read_input(path: Path) -> list[Pattern]:
    tokens = _tokens(path)
    if not tokens:
        raise OISSError(f"empty input file: {path}")
    try:
        count = int(tokens[0], 10)
    except ValueError as exc:
        raise OISSError("PATTERN_NUM must be decimal") from exc
    if count < 0 or len(tokens) != 1 + count * 16:
        raise OISSError(
            f"input declares {count} patterns but contains {len(tokens) - 1} data tokens; expected {count * 16}")
    patterns = []
    offset = 1
    for pattern_index in range(count):
        try:
            words = tuple(Instruction(int(token, 16)) for token in tokens[offset:offset + 8])
            latencies = tuple(int(token, 10) for token in tokens[offset + 8:offset + 16])
        except ValueError as exc:
            raise OISSError(f"invalid number in pattern {pattern_index}") from exc
        try:
            patterns.append(Pattern(words, latencies))
        except OISSError as exc:
            raise OISSError(f"pattern {pattern_index}: {exc}") from exc
        offset += 16
    return patterns


def read_golden(path: Path, expected_count: int) -> list[int]:
    tokens = _tokens(path)
    if len(tokens) != expected_count:
        raise OISSError(f"golden file has {len(tokens)} values; expected {expected_count}")
    values = []
    for index, token in enumerate(tokens):
        try:
            value = int(token, 10)
        except ValueError as exc:
            raise OISSError(f"golden {index} is not decimal: {token!r}") from exc
        if not 0 <= value < 512:
            raise OISSError(f"golden {index} does not fit Ex_cycle[8:0]: {value}")
        values.append(value)
    return values


def read_actual(path: Path, expected_count: int) -> list[tuple[int, tuple[int, ...]]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()
             if line.strip() and not line.lstrip().startswith(("#", "//"))]
    if len(lines) != expected_count:
        raise OISSError(f"actual file has {len(lines)} records; expected {expected_count}")
    result = []
    for index, line in enumerate(lines):
        fields = line.split()
        if len(fields) != 2:
            raise OISSError(f"actual record {index} must contain: Ex_cycle Inst_order_O_hex")
        if any(ch.lower() in "xz" for ch in "".join(fields)):
            raise OISSError(f"actual record {index} contains X/Z: {line!r}")
        try:
            cycle = int(fields[0], 10)
            packed = int(fields[1], 16)
        except ValueError as exc:
            raise OISSError(f"invalid actual record {index}: {line!r}") from exc
        if not 0 <= packed < (1 << 24):
            raise OISSError(f"actual Inst_order_O at record {index} does not fit 24 bits")
        order = tuple((packed >> (3 * k)) & 7 for k in range(8))
        result.append((cycle, order))
    return result


def input_text(patterns: list[Pattern]) -> str:
    lines = [str(len(patterns))]
    for pattern in patterns:
        lines.append(" ".join(f"{instruction.word:03x}" for instruction in pattern.instructions))
        lines.append(" ".join(map(str, pattern.latencies)))
    return "\n".join(lines) + "\n"


def golden_text(values: list[int]) -> str:
    return "\n".join(map(str, values)) + "\n"
