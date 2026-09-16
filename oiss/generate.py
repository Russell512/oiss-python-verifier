"""Deterministic TA-compatible edge/random pattern generation."""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from .formats import golden_text, input_text
from .model import (LEGAL_LATENCIES, Instruction, OISSError, Pattern,
                    dependency_structure, solve, validate_order)


def _latencies(rng: random.Random, index: int) -> tuple[int, ...]:
    variant = index % 4
    if variant == 0:
        return tuple(low for low, _ in LEGAL_LATENCIES)
    if variant == 1:
        return tuple(high for _, high in LEGAL_LATENCIES)
    if variant == 2:
        return tuple((low if opcode % 2 == 0 else high)
                     for opcode, (low, high) in enumerate(LEGAL_LATENCIES))
    return tuple(rng.randint(low, high) for low, high in LEGAL_LATENCIES)


def _instruction(opcode: int, register: int, address: int, rng: random.Random) -> Instruction:
    if opcode <= 3:
        rs = rt = rd = register
    elif opcode == 4:  # LOAD address is immediate; rd carries the dependency.
        rs, rt, rd = address >> 3, address & 7, register
    elif opcode == 5:  # STORE address is immediate; rd is its only register read.
        rs, rt, rd = address >> 3, address & 7, register
    elif opcode == 6:
        rs = rt = register
        rd = rng.randrange(8)  # Signed branch offset; not a register.
    else:
        return Instruction((7 << 9) | rng.randrange(1 << 9))
    return Instruction((opcode << 9) | (rs << 6) | (rt << 3) | rd)


def _no_dependency(rng: random.Random, index: int) -> tuple[Instruction, ...]:
    # Every non-JUMP instruction owns a private register, preventing cross-instruction edges.
    result = []
    for position in range(8):
        opcode = (position + index) % 8
        result.append(_instruction(opcode, position, position, rng))
    rng.shuffle(result)
    return tuple(result)


def _chain_instruction(rng: random.Random, index: int, rank: int,
                       register: int, terminal: bool, address: int) -> Instruction:
    # Non-terminal nodes must write the chain register. A terminal may instead read it.
    opcode = ((index + rank) % 7 if terminal else (index + rank) % 5)
    return _instruction(opcode, register, address, rng)


def _one_chain(rng: random.Random, index: int) -> tuple[Instruction, ...]:
    length = 2 + (index % 7)
    members = set(rng.sample(range(8), length))
    result: list[Instruction | None] = [None] * 8
    chain_positions = sorted(members)
    for rank, position in enumerate(chain_positions):
        result[position] = _chain_instruction(
            rng, index, rank, 0, rank == length - 1, position)
    private_register = 1
    for position in range(8):
        if result[position] is None:
            opcode = (index + position * 3) % 8
            result[position] = _instruction(
                opcode, private_register, position, rng)
            private_register += 1
    return tuple(item for item in result if item is not None)


def _two_chains(rng: random.Random, index: int) -> tuple[Instruction, ...]:
    first_length = 2 + (index % 5)  # Both chains contain at least two instructions.
    first = set(rng.sample(range(8), first_length))
    groups = (sorted(first), sorted(set(range(8)) - first))
    result: list[Instruction | None] = [None] * 8
    for register, positions in enumerate(groups):
        for rank, position in enumerate(positions):
            result[position] = _chain_instruction(
                rng, index + register * 3, rank, register,
                rank == len(positions) - 1, position)
    return tuple(item for item in result if item is not None)


def generate_cases(count: int = 1000, seed: int = 42) -> list[Pattern]:
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise OISSError("--count must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise OISSError("--seed must be an integer")
    rng = random.Random(seed)
    builders = (_no_dependency, _one_chain, _two_chains)
    patterns = []
    for index in range(count):
        pattern = Pattern(builders[index % 3](rng, index), _latencies(rng, index))
        expected_structure = ("none", "one-chain", "two-chains")[index % 3]
        actual_structure = dependency_structure(pattern)
        if actual_structure != expected_structure:
            raise AssertionError(
                f"generator bug at {index}: expected {expected_structure}, got {actual_structure}")
        patterns.append(pattern)
    return patterns


def write_generated(patterns: list[Pattern], out: Path, seed: int, *, force: bool = False) -> dict:
    if out.exists() and not out.is_dir():
        raise OISSError(f"output path is not a directory: {out}")
    if out.exists() and any(out.iterdir()) and not force:
        raise OISSError(f"refusing to overwrite non-empty directory {out}; use --force")
    out.mkdir(parents=True, exist_ok=True)

    solutions = []
    structures = Counter()
    opcodes = Counter()
    dependency_types = Counter()
    for index, pattern in enumerate(patterns):
        result = solve(pattern)
        validate_order(pattern, result.order, result.cycle, index, result.cycle)
        structure = dependency_structure(pattern)
        structures[structure] += 1
        opcodes.update(instruction.opcode for instruction in pattern.instructions)
        for earlier, first in enumerate(pattern.instructions):
            for later in range(earlier + 1, 8):
                second = pattern.instructions[later]
                if first.write_mask & second.read_mask:
                    dependency_types["RAW"] += 1
                if first.read_mask & second.write_mask:
                    dependency_types["WAR"] += 1
                if first.write_mask & second.write_mask:
                    dependency_types["WAW"] += 1
        solutions.append(result)

    input_data = input_text(patterns)
    output_data = golden_text([solution.cycle for solution in solutions])
    solution_data = "\n".join(
        f"{solution.cycle} " + " ".join(map(str, solution.order))
        for solution in solutions) + "\n"
    (out / "input.txt").write_text(input_data, encoding="ascii")
    (out / "output.txt").write_text(output_data, encoding="ascii")
    (out / "solutions.txt").write_text(solution_data, encoding="ascii")
    manifest = {
        "patterns": len(patterns), "seed": seed,
        "dependency_structures": dict(sorted(structures.items())),
        "opcode_counts": {str(key): value for key, value in sorted(opcodes.items())},
        "dependency_type_hits": dict(sorted(dependency_types.items())),
        "sha256": {
            "input.txt": hashlib.sha256(input_data.encode("ascii")).hexdigest(),
            "output.txt": hashlib.sha256(output_data.encode("ascii")).hexdigest(),
            "solutions.txt": hashlib.sha256(solution_data.encode("ascii")).hexdigest(),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
