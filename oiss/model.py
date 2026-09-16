"""Exact combinational scheduling model used by Real_Lab1/PATTERN.v."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Iterable, Sequence

LEGAL_LATENCIES = ((1, 5), (1, 5), (20, 40), (30, 50),
                   (6, 10), (6, 10), (2, 4), (1, 1))


class OISSError(ValueError):
    pass


@dataclass(frozen=True)
class Instruction:
    word: int

    def __post_init__(self) -> None:
        if isinstance(self.word, bool) or not isinstance(self.word, int) or not 0 <= self.word < 4096:
            raise OISSError(f"instruction must be a 12-bit integer, got {self.word!r}")

    @property
    def opcode(self) -> int:
        return self.word >> 9

    @property
    def rs(self) -> int:
        return (self.word >> 6) & 7

    @property
    def rt(self) -> int:
        return (self.word >> 3) & 7

    @property
    def rd(self) -> int:
        return self.word & 7

    @property
    def read_mask(self) -> int:
        if self.opcode <= 3:
            return (1 << self.rs) | (1 << self.rt)
        if self.opcode == 5:  # STORE data source; rs/rt form an immediate address.
            return 1 << self.rd
        if self.opcode == 6:  # BRANCH compares rs and rt; rd is an immediate.
            return (1 << self.rs) | (1 << self.rt)
        return 0

    @property
    def write_mask(self) -> int:
        if self.opcode <= 4:  # ALU and LOAD write rd.
            return 1 << self.rd
        return 0


@dataclass(frozen=True)
class Pattern:
    instructions: tuple[Instruction, ...]
    latencies: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.instructions) != 8 or len(self.latencies) != 8:
            raise OISSError("each pattern requires exactly 8 instructions and 8 opcode latencies")
        for opcode, (value, bounds) in enumerate(zip(self.latencies, LEGAL_LATENCIES)):
            if isinstance(value, bool) or not isinstance(value, int) or not bounds[0] <= value <= bounds[1]:
                raise OISSError(
                    f"opcode {opcode} latency {value!r} is outside {bounds[0]}..{bounds[1]}")

    @property
    def predecessors(self) -> tuple[int, ...]:
        result = [0] * 8
        for i, earlier in enumerate(self.instructions):
            for j in range(i + 1, 8):
                later = self.instructions[j]
                raw = earlier.write_mask & later.read_mask
                war = earlier.read_mask & later.write_mask
                waw = earlier.write_mask & later.write_mask
                if raw or war or waw:
                    result[j] |= 1 << i
        return tuple(result)

    @property
    def inst_seq_i(self) -> int:
        return sum(inst.word << (12 * i) for i, inst in enumerate(self.instructions))

    @property
    def inst_latency_i(self) -> int:
        return sum(value << (6 * i) for i, value in enumerate(self.latencies))


@dataclass(frozen=True)
class Schedule:
    order: tuple[int, ...]
    cycle: int
    starts: tuple[int, ...]
    finishes: tuple[int, ...]

    @property
    def packed_order(self) -> int:
        return sum(index << (3 * position) for position, index in enumerate(self.order))


def dependency_structure(pattern: Pattern) -> str:
    """Return the TA graph class: none, one-chain, two-chains, or other."""
    predecessors = pattern.predecessors
    adjacent = [set() for _ in range(8)]
    for later, mask in enumerate(predecessors):
        for earlier in range(later):
            if mask & (1 << earlier):
                adjacent[earlier].add(later)
                adjacent[later].add(earlier)

    components = []
    unseen = set(range(8))
    while unseen:
        stack = [unseen.pop()]
        component = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacent[current]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
        components.append(tuple(sorted(component)))

    nontrivial = [component for component in components if len(component) > 1]
    if not nontrivial:
        return "none"

    reach = list(predecessors)
    for later in range(8):
        for earlier in range(later):
            if reach[later] & (1 << earlier):
                reach[later] |= reach[earlier]

    def is_chain(component: tuple[int, ...]) -> bool:
        return all(reach[later] & (1 << earlier)
                   for earlier, later in zip(component, component[1:]))

    if len(nontrivial) == 1 and is_chain(nontrivial[0]):
        return "one-chain"
    if (len(nontrivial) == 2 and sum(map(len, nontrivial)) == 8
            and all(is_chain(component) for component in nontrivial)):
        return "two-chains"
    return "other"


def schedule_order(pattern: Pattern, order: Sequence[int]) -> Schedule:
    order = tuple(order)
    if len(order) != 8 or set(order) != set(range(8)):
        raise OISSError("instruction order must be a permutation of 0..7")
    position = [0] * 8
    for k, index in enumerate(order):
        position[index] = k
    predecessors = pattern.predecessors
    for current, mask in enumerate(predecessors):
        for previous in range(8):
            if mask & (1 << previous) and position[previous] >= position[current]:
                raise OISSError(f"order violates dependency I{previous} -> I{current}")

    starts = [0] * 8
    finishes = [0] * 8
    completion = 0
    for k, current in enumerate(order):
        issue_ready = 0 if k == 0 else starts[order[k - 1]] + 1
        dependency_ready = max(
            (finishes[i] for i in range(8) if predecessors[current] & (1 << i)),
            default=0,
        )
        starts[current] = max(issue_ready, dependency_ready)
        finishes[current] = starts[current] + pattern.latencies[pattern.instructions[current].opcode]
        completion = max(completion, finishes[current])
    return Schedule(order, completion, tuple(starts), tuple(finishes))


def solve(pattern: Pattern) -> Schedule:
    """Enumerate every legal issue order; eight instructions make this at most 8! cases."""
    predecessors = pattern.predecessors
    if not any(predecessors):
        order = tuple(sorted(range(8),
                             key=lambda i: (-pattern.latencies[pattern.instructions[i].opcode], i)))
        return schedule_order(pattern, order)
    best: Schedule | None = None
    for order in permutations(range(8)):
        issued = 0
        legal = True
        for current in order:
            if predecessors[current] & ~issued:
                legal = False
                break
            issued |= 1 << current
        if not legal:
            continue
        starts = [0] * 8
        finishes = [0] * 8
        completion = 0
        for k, current in enumerate(order):
            issue_ready = 0 if k == 0 else starts[order[k - 1]] + 1
            mask = predecessors[current]
            dependency_ready = max((finishes[i] for i in range(8) if mask & (1 << i)), default=0)
            starts[current] = max(issue_ready, dependency_ready)
            finishes[current] = starts[current] + pattern.latencies[pattern.instructions[current].opcode]
            completion = max(completion, finishes[current])
        if best is None or completion < best.cycle:
            best = Schedule(tuple(order), completion, tuple(starts), tuple(finishes))
    if best is None:  # Edges always point from a lower to a higher original index.
        raise OISSError("dependency graph has no legal order")
    return best


def _execute(pattern: Pattern, order: Iterable[int], pattern_index: int) -> tuple[tuple[int, ...], tuple[int, ...], int]:
    registers = [(((pattern_index + 1) * 0x1F3D) + r * 0x1357 + 0x2468) & 0xFFFF
                 for r in range(8)]
    memory = [(((pattern_index + 1) * 0x00D3) + m * 0x0101 + 0x55AA) & 0xFFFF
              for m in range(64)]
    pc = (0x1000 + pattern_index) & 0xFFFF
    for index in order:
        inst = pattern.instructions[index]
        op, rs, rt, rd = inst.opcode, inst.rs, inst.rt, inst.rd
        if op == 0:
            registers[rd] = (registers[rs] + registers[rt]) & 0xFFFF
            pc = (pc + 1) & 0xFFFF
        elif op == 1:
            registers[rd] = (registers[rs] - registers[rt]) & 0xFFFF
            pc = (pc + 1) & 0xFFFF
        elif op == 2:
            registers[rd] = (registers[rs] * registers[rt]) & 0xFFFF
            pc = (pc + 1) & 0xFFFF
        elif op == 3:
            registers[rd] = 0 if registers[rt] == 0 else registers[rs] // registers[rt]
            pc = (pc + 1) & 0xFFFF
        elif op == 4:
            registers[rd] = memory[(inst.word >> 3) & 0x3F]
            pc = (pc + 1) & 0xFFFF
        elif op == 5:
            memory[(inst.word >> 3) & 0x3F] = registers[rd]
            pc = (pc + 1) & 0xFFFF
        elif op == 6:
            offset = rd - 8 if rd & 4 else rd
            pc = (pc + 1 + offset if registers[rs] == registers[rt] else pc + 1) & 0xFFFF
        else:
            immediate = inst.word & 0x1FF
            if immediate & 0x100:
                immediate -= 0x200
            pc = (pc + immediate) & 0xFFFF
    return tuple(registers), tuple(memory), pc


def validate_order(pattern: Pattern, order: Sequence[int], cycle: int,
                   pattern_index: int = 0, expected_cycle: int | None = None) -> Schedule:
    if isinstance(cycle, bool) or not isinstance(cycle, int) or not 0 <= cycle < 512:
        raise OISSError("Ex_cycle must be a 9-bit integer")
    result = schedule_order(pattern, order)
    if result.cycle != cycle:
        raise OISSError(f"order completes in {result.cycle}, not submitted Ex_cycle {cycle}")
    if expected_cycle is not None and cycle != expected_cycle:
        raise OISSError(f"Ex_cycle {cycle} does not match golden minimum {expected_cycle}")
    if _execute(pattern, range(8), pattern_index) != _execute(pattern, order, pattern_index):
        raise OISSError("reordered execution does not match the original-order pseudo CPU")
    return result
