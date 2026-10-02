"""How much of the 0.129 -> 0.080 move is the `arith` stratum alone?

The 2026-08-16 reparameterization swapped the recovery instrument from the
whole-file ceiling matcher to the real extractor. Every class got missier, yet
the standardized gap SHRANK, and it shrank in the direction that makes H2
easier to support: the 2.0x support threshold fell from 0.258 to 0.160. A move
that favours the hypothesis is exactly the move that has to be explained
before its constant is frozen.

The explanation on offer is that the extractor's extra blind spot is a nearly
constant +0.20 in every stratum EXCEPT `arith` (+0.148), and `arith` is 76.4%
of the machine mix against 0.7% of the human mix, so a near-uniform penalty
cancels in the difference and only the arith-specific shortfall survives.
This module tests that account three ways, in increasing order of severity.

  1. COUNTERFACTUAL. Set arith's penalty to the flat +0.20 the other strata
     show and restandardize. If the account is right, the gap should return
     to roughly its ceiling-matcher value.

  2. MECHANISM, hypothesis A -- inline hint lists. `nlinarith [sq_nonneg ...]`
     names its premises in source where a simp-closed proof does not, so arith
     premises should survive the narrowing from file scope to declaration
     scope. FALSIFIED HERE, and reported rather than dropped: arith's
     hint-list recall is 0.0131 against simp's 0.0274, and hint lists carry
     2.4% of arith's recovered targets against 5.0% of simp's. The
     mechanism is real in the sense that hint lists exist; it is far too small
     to carry the effect.

  3. MECHANISM, hypothesis B -- proof length. `arith` declaration blocks have
     a median length of 671 characters against 317 (simp), 231 (other) and
     221 (none). Declaration-scope matching searches the block, so a longer
     block loses less when the scope narrows from the whole file. Scope loss
     is strongly monotone in block length WITHIN every class -- arith runs
     0.415 -> 0.078 across the length bins -- which makes length the dominant
     axis, larger than any between-class difference. Standardizing every class
     onto the arith length mix cuts the arith-simp scope gap from 0.073 to
     0.045, so length accounts for roughly 38% of it and a genuine class
     effect carries the rest.

CONSEQUENCE, and the reason this module exists. `INSTRUMENT_MISS_RATE_BY_CLASS`
is not length-controlled, and the two corpora differ in both class mix and
length distribution at once. CLAUDE.md: "Control for proof length everywhere.
Uncontrolled length differences are the obvious reviewer objection." The
reference line inherits that objection until the rates are cut within length
strata. That is why H2_INSTRUMENT_REFERENCE is provisional and not frozen.

Instrument validation, not an H2 metric. Nothing here compiles Lean.
"""

from __future__ import annotations

import collections
import random
import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from src import config
from src.analysis import tactic_strata as ts
from src.extract import ceiling, decl_source
from src.extract import source as src_mod
from src.graph import load

# Block-length bins, in characters. Chosen to put a usable number of `arith`
# declarations in each; they are a reporting grid, not a fitted control.
LENGTH_BINS = ((0, 200), (200, 400), (400, 800), (800, 1_600), (1_600, None))

# `tactic [` -- the opening of a hint list. Longest-first so `simp_all` is not
# matched as `simp`.
_TACTIC_BRACKET = re.compile(
    r"\b("
    + "|".join(sorted(config.AUTOMATION_TACTICS, key=len, reverse=True))
    + r")\b\s*\["
)


def bin_label(n: int) -> str:
    for lo, hi in LENGTH_BINS:
        if hi is None or lo <= n < hi:
            return f"{lo}-{hi}" if hi is not None else f"{lo}+"
    return "?"


BIN_LABELS = tuple(
    f"{lo}-{hi}" if hi is not None else f"{lo}+" for lo, hi in LENGTH_BINS
)


def hint_regions(body: str) -> str:
    """Concatenated contents of every `tactic [...]` hint list in the body.

    Brackets are balanced explicitly rather than matched with `[^\\]]*`,
    because hint lists nest (`simp [List.map_cons, foo [bar]]`) and the lazy
    form would truncate at the first inner close.
    """
    out: list[str] = []
    for m in _TACTIC_BRACKET.finditer(body):
        i = m.end() - 1
        depth = 0
        for j in range(i, len(body)):
            if body[j] == "[":
                depth += 1
            elif body[j] == "]":
                depth -= 1
                if depth == 0:
                    out.append(body[i + 1:j])
                    break
    return "\n".join(out)


@dataclass(frozen=True)
class ProbeRecord:
    """One human declaration, with the target-level facts all three tests need."""

    name: str
    tactic_class: str
    block_chars: int
    targets: int
    in_file: int            # target name occurs somewhere in the module
    in_block: int           # ... and inside the declaration block
    in_hint: int            # ... and inside a `tactic [...]` hint list
    hit: int                # recovered by the real extractor
    hit_and_hint: int
    file_only_same_module: int   # of (in_file & ~in_block), declared here too
    file_only: int


def collect(
    cap: int = ts.CLASS_SAMPLE_CAP, seed: int = config.RANDOM_SEED
) -> list[ProbeRecord]:
    """Same class-targeted draw as `tactic_strata.collect_by_class`.

    Deliberately the same sample and the same seed: these numbers explain a
    move in that module's output, so a different draw would leave the
    explanation and the thing explained measured on different populations.
    """
    g = ts._explicit_graph()
    _, mathematical = load.split_hub_layers(g)
    known = frozenset(load.declaration_names(g))
    index, block_index, _ = ts._human_census()

    buckets: dict[str, list[str]] = collections.defaultdict(list)
    for name, tactics in index.items():
        for cls in ts.classes_used(tactics) or {config.TACTIC_CLASS_NONE}:
            buckets[cls].append(name)
    rng = random.Random(seed)
    picked: set[str] = set()
    for cls in ts.ALL_CLASSES:
        names = sorted(buckets[cls])
        picked.update(rng.sample(names, min(cap, len(names))))

    out: list[ProbeRecord] = []
    for decl in sorted(picked):
        block = block_index.get(decl)
        if block is None:
            continue
        module = g.nodes[decl]["file_module"]
        text = src_mod.read_module_source(module)
        if text is None:
            continue
        hints = hint_regions(decl_source.proof_body(block))
        found = ts.audit.extract(block, known, decl_name=decl, file_text=text)
        c: collections.Counter = collections.Counter()
        for target in g.successors(decl):
            if target not in mathematical:
                continue
            c["targets"] += 1
            f = bool(ceiling.name_or_suffix_occurs(target, text))
            b = bool(ceiling.name_or_suffix_occurs(target, block))
            h = bool(hints) and bool(ceiling.name_or_suffix_occurs(target, hints))
            hit = bool(
                target in found.resolved
                or ceiling.last_component(target) in found.suffix_tokens
            )
            c["in_file"] += f
            c["in_block"] += b
            c["in_hint"] += h
            c["hit"] += hit
            c["hit_and_hint"] += hit and h
            if f and not b:
                c["file_only"] += 1
                c["file_only_same_module"] += (
                    g.nodes[target].get("file_module") == module
                )
        if not c["targets"]:
            continue
        out.append(ProbeRecord(
            name=decl,
            tactic_class=ts.assign_class(index[decl]),
            block_chars=len(block),
            targets=c["targets"], in_file=c["in_file"], in_block=c["in_block"],
            in_hint=c["in_hint"], hit=c["hit"], hit_and_hint=c["hit_and_hint"],
            file_only_same_module=c["file_only_same_module"],
            file_only=c["file_only"],
        ))
    return out


# --- test 1: the counterfactual ------------------------------------------

def counterfactual_gap(
    rates: dict[str, float],
    ceiling_rates: dict[str, float],
    human_mix: dict[str, float],
    machine_mix: dict[str, float],
    arith_penalty: float,
) -> tuple[float, float, float]:
    """Restandardize with arith's extractor penalty forced to `arith_penalty`.

    Every other stratum keeps its measured extractor rate. This isolates the
    arith-specific shortfall and nothing else.
    """
    cf = dict(rates)
    cf["arith"] = ceiling_rates["arith"] + arith_penalty
    h = ts.standardize(cf, human_mix)
    m = ts.standardize(cf, machine_mix)
    return h, m, m - h


def penalty_table(
    rates: dict[str, float],
    reachable: dict[str, float],
    ceiling_rates: dict[str, float],
) -> pd.DataFrame:
    """Split each stratum's extractor penalty into scope and resolution.

    scope       whole file -> declaration block, same substring matcher
    resolution  substring -> identifier resolution, same declaration scope

    Both are properties E3 lives with; the split says which one carries the
    arith deviation. It is scope: arith +0.088 against a non-arith mean of
    +0.136, while the resolution component is near-uniform.
    """
    rows = []
    for cls in ts.ALL_CLASSES:
        rows.append({
            "class": cls,
            "ceiling": ceiling_rates[cls],
            "reachable": reachable[cls],
            "extractor": rates[cls],
            "penalty_total": rates[cls] - ceiling_rates[cls],
            "penalty_scope": reachable[cls] - ceiling_rates[cls],
            "penalty_resolution": rates[cls] - reachable[cls],
        })
    return pd.DataFrame(rows)


# --- test 2: hint lists ---------------------------------------------------

def hint_attribution(records: Sequence[ProbeRecord]) -> pd.DataFrame:
    """Do arith proofs name their premises in `tactic [...]` hint lists?"""
    rows = []
    for cls in ts.ALL_CLASSES:
        sel = [r for r in records if r.tactic_class == cls]
        if not sel:
            continue
        t = sum(r.targets for r in sel)
        hit = sum(r.hit for r in sel)
        hint = sum(r.in_hint for r in sel)
        both = sum(r.hit_and_hint for r in sel)
        rows.append({
            "class": cls, "declarations": len(sel), "targets": t,
            "targets_in_hint_list": hint,
            "hint_list_recall": hint / t if t else float("nan"),
            "extractor_hits": hit,
            "hint_share_of_hits": both / hit if hit else float("nan"),
        })
    return pd.DataFrame(rows)


# --- test 3: proof length -------------------------------------------------

def scope_loss_by_length(records: Sequence[ProbeRecord]) -> pd.DataFrame:
    """Relative and absolute scope loss, class x block-length bin."""
    rows = []
    for cls in ts.ALL_CLASSES:
        for lab in BIN_LABELS:
            sel = [r for r in records
                   if r.tactic_class == cls and bin_label(r.block_chars) == lab]
            t = sum(r.targets for r in sel)
            f = sum(r.in_file for r in sel)
            b = sum(r.in_block for r in sel)
            rows.append({
                "class": cls, "length_bin": lab, "declarations": len(sel),
                "targets": t,
                "file_recall": f / t if t else float("nan"),
                "block_recall": b / t if t else float("nan"),
                "absolute_loss": (f - b) / t if t else float("nan"),
                "relative_loss": (f - b) / f if f else float("nan"),
            })
    return pd.DataFrame(rows)


def length_standardized_scope_loss(
    records: Sequence[ProbeRecord],
) -> pd.DataFrame:
    """Each class's scope loss, reweighted onto the ARITH length mix.

    If length is the whole story the standardized column is flat. It is not
    flat, so a class effect survives; but arith moves 0.134 -> 0.194, which
    is most of the way to simp, so length is a large part of the story.
    """
    arith = [r for r in records if r.tactic_class == "arith"]
    mix = {
        lab: sum(1 for r in arith if bin_label(r.block_chars) == lab) / len(arith)
        for lab in BIN_LABELS
    }
    rows = []
    for cls in ts.ALL_CLASSES:
        sel = [r for r in records if r.tactic_class == cls]
        if not sel:
            continue
        f = sum(r.in_file for r in sel)
        b = sum(r.in_block for r in sel)
        num = den = 0.0
        for lab in BIN_LABELS:
            cell = [r for r in sel if bin_label(r.block_chars) == lab]
            ct = sum(r.targets for r in cell)
            cf = sum(r.in_file for r in cell)
            cb = sum(r.in_block for r in cell)
            if not ct or not cf:
                continue
            num += mix[lab] * ((cf - cb) / cf)
            den += mix[lab]
        rows.append({
            "class": cls, "declarations": len(sel),
            "median_block_chars": statistics.median(
                r.block_chars for r in sel),
            "raw_relative_loss": (f - b) / f if f else float("nan"),
            "arith_length_standardized": num / den if den else float("nan"),
            "file_only_same_module_share": (
                sum(r.file_only_same_module for r in sel)
                / sum(r.file_only for r in sel)
                if sum(r.file_only for r in sel) else float("nan")
            ),
        })
    return pd.DataFrame(rows)


# --- entry point ----------------------------------------------------------

def main(cap: int = ts.CLASS_SAMPLE_CAP) -> None:
    records = collect(cap)
    strata, _ = ts.collect_by_class(cap)
    rates = ts._rates_dict(ts.partition_miss_rates(strata, hits_of=ts.EXTRACTOR_HITS))
    reach = ts._rates_dict(ts.partition_miss_rates(strata, hits_of=ts.REACHABLE_HITS))
    ceil_ = ts._rates_dict(ts.partition_miss_rates(strata, hits_of=ts.CEILING_HITS))
    human_mix = ts.human_class_mix_census()
    machine_mix = ts.machine_class_mix()

    print("=" * 74)
    print("PENALTY DECOMPOSITION — extractor over ceiling matcher, per stratum")
    print("=" * 74)
    pen = penalty_table(rates, reach, ceil_)
    print(pen.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    non_arith = pen[pen["class"] != "arith"]
    print(f"\nnon-arith mean penalty {non_arith['penalty_total'].mean():+.4f}"
          f"   arith {float(pen.loc[pen['class'] == 'arith', 'penalty_total'].iloc[0]):+.4f}")
    print(f"non-arith mean SCOPE   {non_arith['penalty_scope'].mean():+.4f}"
          f"   arith {float(pen.loc[pen['class'] == 'arith', 'penalty_scope'].iloc[0]):+.4f}")
    print(f"non-arith mean RESOLN  {non_arith['penalty_resolution'].mean():+.4f}"
          f"   arith {float(pen.loc[pen['class'] == 'arith', 'penalty_resolution'].iloc[0]):+.4f}")

    print()
    print("=" * 74)
    print("TEST 1 — counterfactual: give arith the flat +0.20 penalty")
    print("=" * 74)
    h0, m0, g0 = (ts.standardize(rates, human_mix),
                  ts.standardize(rates, machine_mix), 0.0)
    g0 = m0 - h0
    _, _, g_ceil = (0, 0, ts.standardize(ceil_, machine_mix)
                    - ts.standardize(ceil_, human_mix))
    print(f"{'basis':<34}{'human':>9}{'machine':>10}{'gap':>10}")
    print(f"{'ceiling matcher (2026-08-13)':<34}"
          f"{ts.standardize(ceil_, human_mix):>9.4f}"
          f"{ts.standardize(ceil_, machine_mix):>10.4f}{g_ceil:>+10.4f}")
    print(f"{'real extractor (measured)':<34}{h0:>9.4f}{m0:>10.4f}{g0:>+10.4f}")
    flat = float(non_arith["penalty_total"].mean())
    for pen_val, lab in ((0.20, "arith penalty := +0.200 flat"),
                         (flat, f"arith penalty := {flat:+.4f} (non-arith mean)")):
        h, m, g = counterfactual_gap(rates, ceil_, human_mix, machine_mix, pen_val)
        print(f"{lab:<34}{h:>9.4f}{m:>10.4f}{g:>+10.4f}")
        print(f"{'':<34}-> arith deviation explains {g - g0:+.4f} of the "
              f"{g0 - g_ceil:+.4f} move  ({(g - g0) / (g_ceil - g0):.0%})")

    print()
    print("=" * 74)
    print("TEST 2 — hypothesis A: inline hint lists. FALSIFIED")
    print("=" * 74)
    hints = hint_attribution(records)
    print(hints.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("\narith's hint-list recall is BELOW simp's. Hint lists exist but are "
          "far too\nsmall to carry the deviation. Reported, not dropped.")

    print()
    print("=" * 74)
    print("TEST 3 — hypothesis B: proof length. RELATIVE scope loss by bin")
    print("=" * 74)
    by_len = scope_loss_by_length(records)
    wide = by_len.pivot(index="class", columns="length_bin",
                        values="relative_loss").reindex(ts.ALL_CLASSES)[list(BIN_LABELS)]
    print(wide.to_string(float_format=lambda x: f"{x:.3f}"))
    print("\nMonotone in length within EVERY class — a larger swing than any "
          "between-class\ndifference. Length is the dominant axis.")

    print()
    std = length_standardized_scope_loss(records)
    print(std.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    a = std.set_index("class")
    raw_gap = a.loc["simp", "raw_relative_loss"] - a.loc["arith", "raw_relative_loss"]
    adj_gap = (a.loc["simp", "arith_length_standardized"]
               - a.loc["arith", "arith_length_standardized"])
    print(f"\narith-vs-simp scope gap: raw {raw_gap:.4f} -> length-standardized "
          f"{adj_gap:.4f}")
    print(f"length accounts for {1 - adj_gap / raw_gap:.0%} of it; a class effect "
          f"carries the rest.")
    print("\nCONSEQUENCE: INSTRUMENT_MISS_RATE_BY_CLASS is not length-controlled "
          "and the\ncorpora differ in class mix AND length at once. "
          "H2_INSTRUMENT_REFERENCE stays\nPROVISIONAL until the rates are cut "
          "within length strata (CLAUDE.md §6).")

    _write(pen, hints, by_len, std, rates, ceil_, human_mix, machine_mix, g0, g_ceil)


def _write(pen, hints, by_len, std, rates, ceil_, human_mix, machine_mix,
           g0, g_ceil) -> None:
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    pen.to_csv(config.RESULTS / "instrument_penalty_decomposition.csv", index=False)
    hints.to_csv(config.RESULTS / "arith_hint_list_attribution.csv", index=False)
    by_len.to_csv(config.RESULTS / "scope_loss_by_length.csv", index=False)
    std.to_csv(config.RESULTS / "scope_loss_length_standardized.csv", index=False)

    rows = []
    flat = float(pen[pen["class"] != "arith"]["penalty_total"].mean())
    for pen_val, lab in ((None, "measured"), (0.20, "flat_0.20"),
                         (flat, "non_arith_mean")):
        if pen_val is None:
            h = ts.standardize(rates, human_mix)
            m = ts.standardize(rates, machine_mix)
        else:
            h, m, _ = counterfactual_gap(
                rates, ceil_, human_mix, machine_mix, pen_val)
        rows.append({
            "arith_penalty_basis": lab,
            "arith_rate": rates["arith"] if pen_val is None
            else ceil_["arith"] + pen_val,
            "imputed_human": h, "imputed_machine": m, "gap": m - h,
            "gap_ceiling_matcher": g_ceil, "gap_measured": g0,
            "share_of_move_explained": (
                float("nan") if pen_val is None else (m - h - g0) / (g_ceil - g0)
            ),
        })
    pd.DataFrame(rows).to_csv(
        config.RESULTS / "arith_counterfactual_gap.csv", index=False)
    print(f"\nwrote 5 CSVs to {config.RESULTS}")


if __name__ == "__main__":
    import sys

    main(int(sys.argv[1]) if len(sys.argv) > 1 else ts.CLASS_SAMPLE_CAP)
