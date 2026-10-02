"""Ceiling analysis: the strict upper bound on extraction retention.

Runs BEFORE any parser exists, and deliberately needs none.

For a sampled declaration we take its WHOLE source file and ask, for each of
its explicit dependency targets, whether that name appears anywhere in the
file text. Whole-file matching massively over-counts — every other
declaration in the file supplies names too — and that is exactly the point.
It is an upper bound no per-declaration extractor can beat, so if the
mathematical-layer ceiling already sits below the gate, source-visible
extraction cannot pass and the CLAUDE.md §7 fallback should be taken
immediately rather than after a week of parser work.

The matcher here is also reused for typed_rate (audit miss classification),
which is why it must stay independent of the real parser: a broken parser
must not be able to manufacture "elaborator-inserted" labels.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass, field

import networkx as nx

from src import config
from src.extract import source as src_mod
from src.graph import load

# Lean identifiers may contain letters, digits, _, ', ! and ?, and compose
# with dots. Two boundary classes are needed, and conflating them costs real
# hits:
#
#   FQN match       - a leading dot must NOT be allowed, or the FQN
#                     Bar.baz would match inside Foo.Bar.baz.
#   suffix match    - a leading dot MUST be allowed, because dot notation is
#                     how mathlib usually cites: `p.primeCompl` is a genuine
#                     source occurrence of Ideal.primeCompl.
_IDENT_CHAR = r"[A-Za-z0-9_.'!?]"
_IDENT_CHAR_NODOT = r"[A-Za-z0-9_'!?]"


def _occurrence_pattern(name: str, boundary: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!{boundary}){re.escape(name)}(?!{boundary})")


def name_occurs(name: str, text: str) -> bool:
    """Word-boundary occurrence of a fully-qualified name in source text."""
    return _occurrence_pattern(name, _IDENT_CHAR).search(text) is not None


def suffix_occurs(name: str, text: str) -> bool:
    """Occurrence of a bare name, permitting a qualifying dot before it."""
    return _occurrence_pattern(name, _IDENT_CHAR_NODOT).search(text) is not None


def last_component(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def name_or_suffix_occurs(name: str, text: str) -> bool:
    """Loose match: the FQN, or its last component written unqualified.

    Deliberately generous. `Eq.mpr` counts as present if the file contains
    `.mpr` anywhere, which is wrong as extraction but correct as a bound.
    """
    if name_occurs(name, text):
        return True
    tail = last_component(name)
    return tail != name and suffix_occurs(tail, text)


@dataclass
class CeilingResult:
    sample_size: int
    # (matched, total) per layer, under the loose matcher
    loose: dict[str, tuple[int, int]] = field(default_factory=dict)
    # under the strict matcher (fully-qualified occurrences only)
    strict: dict[str, tuple[int, int]] = field(default_factory=dict)
    unreachable_targets: int = 0
    skipped_decls: int = 0
    top_missed: list[tuple[str, int]] = field(default_factory=list)

    @staticmethod
    def _rate(pair: tuple[int, int]) -> float:
        matched, total = pair
        return matched / total if total else 0.0

    def report(self) -> str:
        lines = [
            (
                f"ceiling analysis  n={self.sample_size} declarations "
                f"({self.skipped_decls} skipped, no source file)"
            ),
            "",
            f"{'layer':<26}{'loose':>18}{'strict':>18}",
        ]
        for layer in ("mathematical", "infrastructure", "all_explicit"):
            lo, st = self.loose[layer], self.strict[layer]
            lines.append(
                f"{layer:<26}"
                f"{self._rate(lo):>7.3f} ({lo[0]:>4}/{lo[1]:<5})"
                f"{self._rate(st):>9.3f} ({st[0]:>4}/{st[1]:<5})"
            )
        lines += [
            "",
            f"targets not in the declaration set: {self.unreachable_targets}",
            "",
            "most-missed targets (strict, mathematical + infrastructure):",
        ]
        lines += [f"  {n:<44}{c:>5}" for n, c in self.top_missed]
        return "\n".join(lines)


def sample_declarations(
    g: nx.DiGraph,
    n: int,
    seed: int = config.RANDOM_SEED,
) -> list[str]:
    """Tactic-proof mathlib theorems with at least one explicit dependency.

    Stratified over LENGTH_CONTROL_BINS on tactic_count so that one-line
    proofs, which are abundant and mechanically easy, cannot dominate.
    Automation-closed proofs are INCLUDED — they are stratified over, never
    excluded (CLAUDE.md §6).
    """
    eligible = [
        name
        for name, a in g.nodes(data=True)
        if a["kind"] == "theorem"
        and a["file_module"].startswith(config.MATHLIB_MODULE_PREFIX)
        and a["is_tactic_proof"]
        and g.out_degree(name) > 0
    ]
    bins = config.LENGTH_CONTROL_BINS
    strata: dict[int, list[str]] = {i: [] for i in range(len(bins))}
    for name in eligible:
        tc = g.nodes[name]["tactic_count"]
        idx = next((i for i, b in enumerate(bins) if tc <= b), len(bins) - 1)
        strata[idx].append(name)

    rng = random.Random(seed)
    populated = [s for s in strata.values() if s]
    per = max(1, n // len(populated))
    picked: list[str] = []
    for stratum in populated:
        stratum.sort()
        picked += rng.sample(stratum, min(per, len(stratum)))
    rng.shuffle(picked)
    return picked[:n]


def run_ceiling(sample_size: int | None = None) -> CeilingResult:
    n = sample_size or config.CEILING_SAMPLE_SIZE
    g = load.load_explicit_graph()
    _, mathematical = load.split_hub_layers(g)
    known = load.declaration_names(g)

    result = CeilingResult(sample_size=0)
    counts = {
        k: {"loose": [0, 0], "strict": [0, 0]}
        for k in ("mathematical", "infrastructure", "all_explicit")
    }
    missed: Counter[str] = Counter()

    for decl in sample_declarations(g, n):
        text = src_mod.read_module_source(g.nodes[decl]["file_module"])
        if text is None:
            result.skipped_decls += 1
            continue
        result.sample_size += 1

        for target in g.successors(decl):
            if target not in known:
                result.unreachable_targets += 1
                continue
            layer = "mathematical" if target in mathematical else "infrastructure"
            hit_loose = name_or_suffix_occurs(target, text)
            hit_strict = name_occurs(target, text)
            for key in (layer, "all_explicit"):
                counts[key]["loose"][1] += 1
                counts[key]["strict"][1] += 1
                counts[key]["loose"][0] += hit_loose
                counts[key]["strict"][0] += hit_strict
            if not hit_strict:
                missed[target] += 1

    for layer, c in counts.items():
        result.loose[layer] = tuple(c["loose"])
        result.strict[layer] = tuple(c["strict"])
    result.top_missed = missed.most_common(15)
    return result


def write_results(result: CeilingResult) -> None:
    """Commit the ceiling numbers. Small CSV, regenerable from seed."""
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    out = config.RESULTS / "ceiling_analysis.csv"
    rows = ["layer,matcher,matched,total,rate"]
    for layer in ("mathematical", "infrastructure", "all_explicit"):
        for matcher, table in (("loose", result.loose), ("strict", result.strict)):
            m, t = table[layer]
            rows.append(f"{layer},{matcher},{m},{t},{m / t if t else 0:.4f}")
    out.write_text("\n".join(rows) + "\n")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    res = run_ceiling(n)
    print(res.report())
    write_results(res)
