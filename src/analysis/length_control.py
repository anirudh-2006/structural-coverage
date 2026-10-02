"""Length-control the instrument reference: joint standardization on
(tactic class x proof length), not tactic class alone.

WHY THIS EXISTS. `analysis.arith_sensitivity` established that the tactic
partition is substantially a LENGTH proxy: declaration-scope scope-loss is
monotone in block length within EVERY class (arith 0.415 -> 0.078 across the
bins), and that within-class swing is larger than any between-class
difference. Median block chars run arith 679, simp 349, decide 322, other 235,
none 223. So the class-only standardization behind
`H2_INSTRUMENT_REFERENCE = 0.080` was already standardizing on length --
implicitly, unevenly, and without saying so. CLAUDE.md §5 requires length
control on every metric.

WHAT CHANGES. The reference line is a difference of two standardized rates:

    D_m = sum_s w_s^machine r_s  -  sum_s w_s^human r_s

Class-only standardization takes s = class. Joint standardization takes
s = (class, length bin). If the two corpora differ in length distribution
WITHIN a class -- and they do, because machine proofs are competition proofs
-- then the class-only version applies a human class rate that was measured
on a different length mix than the machine proofs it is being applied to.
That is the definition of an uncontrolled confound, and it is the obvious
reviewer objection CLAUDE.md names.

SCOPE PARITY, same rule as everywhere else. Human length is the located
mathlib declaration block (statement + proof). Machine length is the Goedel
`theorem ...` line onward, corpus header EXCLUDED -- the same construction
`spurious_symmetry.machine_declaration_block` uses, and for the same reason:
including the five-line header would add a constant ~200 chars to all 29,750
machine proofs and shift the entire machine corpus up a bin for free.

CELL COLLAPSE. A (class, bin) cell with fewer than `LENGTH_CELL_MIN_N`
declarations does not get its own rate. It falls back to the LENGTH BIN
marginal first -- length is the dominant axis, so a same-length cell of a
different class is the closer neighbour than a same-class cell of a different
length -- then to the overall rate. Every collapse is reported in
`results/length_controlled_cells.csv`, never silent.

This is instrument validation, not an H2 metric, and it runs on the human
corpus only. No metric definition is being tuned after seeing a machine-side
result: the machine corpus enters only as a MIX (its class x length
composition), exactly as it already did as a class mix.
"""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Sequence

import pandas as pd

from src import config
from src.analysis import tactic_strata as ts
from src.analysis.automation_confound import GOEDEL_PARQUET, automation_tactics_in_text
from src.analysis.spurious_symmetry import machine_declaration_block
from src.extract import audit, decl_source

# The length AXIS is a parameter from 2026-08-16. `steps` is primary --
# characters are contaminated by source formatting (overlap coefficient 0.215
# on chars vs 0.856 on steps, analysis.length_overlap) -- and `chars`
# is retained as the sensitivity row.
AXES = {
    "steps": (config.PROOF_STEP_BINS, "tactic_steps"),
    "chars": (config.PROOF_LENGTH_BINS, "block_chars"),
}
PRIMARY_AXIS = "steps"


def _labels(bins) -> tuple[str, ...]:
    return tuple(
        f"{lo}-{hi}" if hi is not None else f"{lo}+" for lo, hi in bins
    )


def bin_label(n: int, axis: str = PRIMARY_AXIS) -> str:
    bins, _ = AXES[axis]
    for lo, hi in bins:
        if hi is None or lo <= n < hi:
            return f"{lo}-{hi}" if hi is not None else f"{lo}+"
    return _labels(bins)[-1]


def record_length(r: ts.DeclRecord, axis: str = PRIMARY_AXIS) -> int:
    return getattr(r, AXES[axis][1])


def cells(axis: str = PRIMARY_AXIS) -> tuple[tuple[str, str], ...]:
    return tuple(
        (c, b) for c in ts.ALL_CLASSES for b in _labels(AXES[axis][0])
    )


# Back-compat aliases for the character-axis call sites.
BIN_LABELS: tuple[str, ...] = _labels(config.PROOF_STEP_BINS)
CELLS: tuple[tuple[str, str], ...] = cells(PRIMARY_AXIS)


# --- joint rates ----------------------------------------------------------

def joint_miss_rates(
    records: Sequence[ts.DeclRecord],
    precedence: Sequence[str] = config.TACTIC_CLASS_PRECEDENCE,
    hits_of=ts.EXTRACTOR_HITS,
    min_n: int = config.LENGTH_CELL_MIN_N,
    axis: str = PRIMARY_AXIS,
) -> tuple[dict[tuple[str, str], float], pd.DataFrame]:
    """Per-(class, length bin) miss rate, with a reported fallback chain.

    Returns the usable rate per cell and a frame recording, for every cell,
    how many declarations it had and which basis its rate actually came from.
    """
    all_cells = cells(axis)
    labels = _labels(AXES[axis][0])
    by_cell: dict[tuple[str, str], list[ts.DeclRecord]] = {c: [] for c in all_cells}
    for r in records:
        key = (ts.assign_class(r.matched_tactics, precedence),
               bin_label(record_length(r, axis), axis))
        by_cell[key].append(r)

    by_bin: dict[str, list[ts.DeclRecord]] = {b: [] for b in labels}
    for (_, b), recs in by_cell.items():
        by_bin[b] += recs

    overall_rate = ts._rate(records, hits_of)[3]

    rates: dict[tuple[str, str], float] = {}
    rows = []
    for cls, lab in all_cells:
        recs = by_cell[(cls, lab)]
        n, targets, missed, rate = ts._rate(recs, hits_of)
        if n >= min_n and targets:
            basis = "cell"
        else:
            bn, btargets, _, brate = ts._rate(by_bin[lab], hits_of)
            if bn >= min_n and btargets:
                basis, rate = "length_bin_marginal", brate
            else:
                basis, rate = "overall", overall_rate
        rates[(cls, lab)] = rate
        rows.append({
            "class": cls, "length_bin": lab, "declarations": n,
            "targets": targets, "missed": missed,
            "cell_rate": (missed / targets) if targets else float("nan"),
            "rate_used": rate, "basis": basis, "axis": axis,
        })
    return rates, pd.DataFrame(rows)


# --- joint mixes ----------------------------------------------------------

def _length_of(block: str, axis: str) -> int:
    """Block length on the requested axis, identically on both corpora."""
    if axis == "chars":
        return len(block)
    return audit.tactic_steps(decl_source.proof_body(block))


def human_joint_mix_census(
    precedence: Sequence[str] = config.TACTIC_CLASS_PRECEDENCE,
    axis: str = PRIMARY_AXIS,
) -> dict[tuple[str, str], float]:
    """Census over every eligible mathlib tactic proof with a located block."""
    index, block_index, _ = ts._human_census()
    counts = dict.fromkeys(cells(axis), 0)
    total = 0
    for name, tactics in index.items():
        block = block_index.get(name)
        if block is None:
            continue
        counts[(ts.assign_class(tactics, precedence),
                bin_label(_length_of(block, axis), axis))] += 1
        total += 1
    return {k: v / total for k, v in counts.items()}


def machine_joint_mix_census(
    precedence: Sequence[str] = config.TACTIC_CLASS_PRECEDENCE,
    axis: str = PRIMARY_AXIS,
) -> dict[tuple[str, str], float]:
    """Census over all Goedel proofs. Header excluded, per scope parity."""
    df = pd.read_parquet(GOEDEL_PARQUET)
    counts = dict.fromkeys(cells(axis), 0)
    total = 0
    for full in df["full_proof"]:
        block = machine_declaration_block(full)
        if block is None:
            continue
        cls = ts.assign_class(
            automation_tactics_in_text(decl_source.proof_body(block)), precedence
        )
        counts[(cls, bin_label(_length_of(block, axis), axis))] += 1
        total += 1
    return {k: v / total for k, v in counts.items()}


def _standardize(rates: dict, mix: dict) -> float:
    usable = {
        k: w for k, w in mix.items()
        if k in rates and not math.isnan(rates[k])
    }
    total = sum(usable.values())
    if not total:
        return float("nan")
    return sum(w * rates[k] for k, w in usable.items()) / total


def joint_standardized_gap(
    records: Sequence[ts.DeclRecord],
    human_mix: dict,
    machine_mix: dict,
    precedence: Sequence[str] = config.TACTIC_CLASS_PRECEDENCE,
    hits_of=ts.EXTRACTOR_HITS,
    axis: str = PRIMARY_AXIS,
) -> tuple[float, float, float]:
    rates, _ = joint_miss_rates(
        records, precedence, hits_of, config.LENGTH_CELL_MIN_N, axis)
    h = _standardize(rates, human_mix)
    m = _standardize(rates, machine_mix)
    return h, m, m - h


def bootstrap_joint_gap(
    records: Sequence[ts.DeclRecord],
    human_mix: dict,
    machine_mix: dict,
    resamples: int = config.H2_BOOTSTRAP_RESAMPLES,
    seed: int = config.RANDOM_SEED,
    axis: str = PRIMARY_AXIS,
) -> tuple[float, float]:
    """CI on the joint gap, resampling declarations within (class, bin) cell."""
    strata: dict[tuple[str, str], list[ts.DeclRecord]] = {
        c: [] for c in cells(axis)}
    for r in records:
        strata[(ts.assign_class(r.matched_tactics),
                bin_label(record_length(r, axis), axis))].append(r)

    rng = random.Random(seed)
    gaps = []
    for _ in range(resamples):
        draw: list[ts.DeclRecord] = []
        for members in strata.values():
            if not members:
                continue
            draw += [members[rng.randrange(len(members))] for _ in members]
        _, _, gap = joint_standardized_gap(
            draw, human_mix, machine_mix, axis=axis)
        if not math.isnan(gap):
            gaps.append(gap)
    gaps.sort()
    alpha = (1 - config.H2_BOOTSTRAP_CI) / 2
    return (gaps[int(alpha * len(gaps))],
            gaps[min(len(gaps) - 1, int((1 - alpha) * len(gaps)))])


# --- length-only standardization, as a diagnostic -------------------------

def length_only_gap(
    records: Sequence[ts.DeclRecord],
    human_mix: dict,
    machine_mix: dict,
    hits_of=ts.EXTRACTOR_HITS,
    axis: str = PRIMARY_AXIS,
) -> tuple[float, float, float]:
    """Standardize on LENGTH alone, ignoring class.

    If this reproduces most of the class-only gap, the class partition was
    largely a length proxy and the paper has to say so.
    """
    labels = _labels(AXES[axis][0])
    by_bin: dict[str, list[ts.DeclRecord]] = {b: [] for b in labels}
    for r in records:
        by_bin[bin_label(record_length(r, axis), axis)].append(r)
    rates = {b: ts._rate(recs, hits_of)[3] for b, recs in by_bin.items()}

    def collapse(mix: dict) -> dict:
        out = dict.fromkeys(labels, 0.0)
        for (_, b), w in mix.items():
            out[b] += w
        return out

    h = ts.standardize(rates, collapse(human_mix))
    m = ts.standardize(rates, collapse(machine_mix))
    return h, m, m - h


# --- the PRECISION term, same machinery -----------------------------------

def joint_spurious_rates(
    records, precedence=config.TACTIC_CLASS_PRECEDENCE,
    min_n: int = config.LENGTH_CELL_MIN_N, axis: str = PRIMARY_AXIS,
):
    """Per-(class, length bin) SPURIOUS rate. Denominator is resolved premises.

    Same construction as `joint_miss_rates`, different numerator/denominator:
    spurious rate is "what fraction of what the extractor puts into a premise
    set does not belong there", so it is over RESOLVED, not over targets. That
    difference in denominator is exactly why the two components of the
    combined reference line cannot simply be added without a caveat.
    """
    all_cells = cells(axis)
    labels = _labels(AXES[axis][0])
    by_cell = {c: [] for c in all_cells}
    for r in records:
        by_cell[(ts.assign_class(r.matched_tactics, precedence),
                 bin_label(record_length(r, axis), axis))].append(r)
    by_bin = {b: [] for b in labels}
    for (_, b), recs in by_cell.items():
        by_bin[b] += recs

    def rate(recs):
        res = sum(r.resolved for r in recs)
        sp = sum(r.spurious for r in recs)
        return len(recs), res, sp, (sp / res if res else float("nan"))

    _, _, _, overall = rate(records)
    rates, rows = {}, []
    for cls, lab in all_cells:
        recs = by_cell[(cls, lab)]
        n, res, sp, r_ = rate(recs)
        if n >= min_n and res:
            basis = "cell"
        else:
            bn, bres, _, br = rate(by_bin[lab])
            basis, r_ = (("length_bin_marginal", br) if bn >= min_n and bres
                         else ("overall", overall))
        rates[(cls, lab)] = r_
        rows.append({"class": cls, "length_bin": lab, "declarations": n,
                     "resolved": res, "spurious": sp,
                     "rate_used": r_, "basis": basis, "axis": axis})
    return rates, pd.DataFrame(rows)


def joint_spurious_gap(records, human_mix, machine_mix,
                       precedence=config.TACTIC_CLASS_PRECEDENCE,
                       axis: str = PRIMARY_AXIS):
    rates, frame = joint_spurious_rates(
        records, precedence, config.LENGTH_CELL_MIN_N, axis)
    h = _standardize(rates, human_mix)
    m = _standardize(rates, machine_mix)
    return h, m, m - h, frame


def run_spurious(records, axis: str) -> dict:
    """Length-controlled precision term, with the extrapolation diagnostics
    the pre-registered prediction says must be read alongside it."""
    human_mix = human_joint_mix_census(axis=axis)
    machine_mix = machine_joint_mix_census(axis=axis)
    labels = _labels(AXES[axis][0])
    hb = dict.fromkeys(labels, 0.0)
    mb = dict.fromkeys(labels, 0.0)
    for (_, b), w in human_mix.items():
        hb[b] += w
    for (_, b), w in machine_mix.items():
        mb[b] += w

    h, m, gap, frame = joint_spurious_gap(records, human_mix, machine_mix,
                                          axis=axis)
    collapsed = frame[frame["basis"] != "cell"]
    return {
        "axis": axis,
        "overlap_coefficient": sum(min(hb[b], mb[b]) for b in labels),
        "imputed_human": h, "imputed_machine": m, "gap_joint": gap,
        "collapsed_cells": len(collapsed), "total_cells": len(frame),
        "collapsed_human_mix": float(collapsed.apply(
            lambda r: human_mix[(r["class"], r["length_bin"])], axis=1).sum()),
        "collapsed_machine_mix": float(collapsed.apply(
            lambda r: machine_mix[(r["class"], r["length_bin"])], axis=1).sum()),
    }


# --- entry point ----------------------------------------------------------

def run_axis(records, axis: str, verbose: bool = True) -> dict:
    """Everything for one length axis. Returns the row that goes in the CSV."""
    human_mix = human_joint_mix_census(axis=axis)
    machine_mix = machine_joint_mix_census(axis=axis)
    labels = _labels(AXES[axis][0])

    hb = dict.fromkeys(labels, 0.0)
    mb = dict.fromkeys(labels, 0.0)
    for (_, b), w in human_mix.items():
        hb[b] += w
    for (_, b), w in machine_mix.items():
        mb[b] += w

    if verbose:
        print("=" * 78)
        print(f"AXIS: {axis.upper()}"
              + ("   <- PRIMARY (wrap-invariant)" if axis == PRIMARY_AXIS
                 else "   <- sensitivity row (formatting-contaminated)"))
        print("=" * 78)
        print(f"{'bin':<14}{'human':>10}{'machine':>10}{'delta':>10}"
              f"{'overlap':>10}")
        for b in labels:
            print(f"{b:<14}{hb[b]:>10.4f}{mb[b]:>10.4f}"
                  f"{mb[b] - hb[b]:>+10.4f}{min(hb[b], mb[b]):>10.4f}")
        print(f"{'OVERLAP COEF':<14}{'':>10}{'':>10}{'':>10}"
              f"{sum(min(hb[b], mb[b]) for b in labels):>10.4f}")

    _, cells_frame = joint_miss_rates(records, axis=axis)
    collapsed = cells_frame[cells_frame["basis"] != "cell"]

    h_c, m_c, g_c = ts.standardized_gap(
        records, ts.human_class_mix_census(), ts.machine_class_mix())
    h_l, m_l, g_l = length_only_gap(records, human_mix, machine_mix, axis=axis)
    h_j, m_j, g_j = joint_standardized_gap(
        records, human_mix, machine_mix, axis=axis)
    lo, hi = bootstrap_joint_gap(records, human_mix, machine_mix, axis=axis)

    if verbose:
        print()
        print(f"{len(collapsed)} of {len(cells_frame)} cells collapsed, "
              f"carrying "
              f"{collapsed.apply(lambda r: human_mix[(r['class'], r['length_bin'])], axis=1).sum():.4f}"
              f" human / "
              f"{collapsed.apply(lambda r: machine_mix[(r['class'], r['length_bin'])], axis=1).sum():.4f}"
              f" machine mix")
        print()
        print(f"{'standardization':<28}{'human':>10}{'machine':>10}{'D_m':>10}")
        print(f"{'class only':<28}{h_c:>10.4f}{m_c:>10.4f}{g_c:>+10.4f}")
        print(f"{'length only':<28}{h_l:>10.4f}{m_l:>10.4f}{g_l:>+10.4f}")
        print(f"{'class x length (JOINT)':<28}{h_j:>10.4f}{m_j:>10.4f}"
              f"{g_j:>+10.4f}")
        print(f"joint 95% CI [{lo:+.4f}, {hi:+.4f}]")

    sweep = []
    for order in itertools.permutations(config.TACTIC_CLASS_PRECEDENCE):
        _, _, g = joint_standardized_gap(
            records, human_joint_mix_census(order, axis),
            machine_joint_mix_census(order, axis), order, axis=axis)
        sweep.append(g)
    if verbose:
        print(f"precedence band [{min(sweep):+.4f}, {max(sweep):+.4f}]")

    return {
        "axis": axis, "overlap_coefficient": sum(min(hb[b], mb[b]) for b in labels),
        "gap_class_only": g_c, "gap_length_only": g_l, "gap_joint": g_j,
        "ci_low": lo, "ci_high": hi,
        "band_low": min(sweep), "band_high": max(sweep),
        "cells_collapsed": len(collapsed), "cells_total": len(cells_frame),
    }, cells_frame


def main(cap: int = config.LENGTH_CONTROL_CLASS_CAP) -> None:
    records, _ = ts.collect_by_class(cap)

    rows, frames = [], []
    for axis in ("steps", "chars"):
        row, cf = run_axis(records, axis)
        rows.append(row)
        frames.append(cf)
        print()

    print("=" * 78)
    print("VERDICT — does the length control survive a wrap-invariant axis?")
    print("=" * 78)
    frame = pd.DataFrame(rows)
    print(frame.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    steps = frame[frame["axis"] == "steps"].iloc[0]
    chars = frame[frame["axis"] == "chars"].iloc[0]
    print(f"\nD_m on chars {chars['gap_joint']:+.4f} vs on steps "
          f"{steps['gap_joint']:+.4f}")
    print(f"overlap coefficient chars {chars['overlap_coefficient']:.4f} vs "
          f"steps {steps['overlap_coefficient']:.4f}")
    print("\nThe STEPS row is the defensible one: character length is "
          "contaminated by\nmathlib's hand-wrapping and docstrings, which the "
          "machine corpus does not have.")

    config.RESULTS.mkdir(parents=True, exist_ok=True)
    frame.to_csv(config.RESULTS / "length_controlled_reference.csv", index=False)
    pd.concat(frames, ignore_index=True).to_csv(
        config.RESULTS / "length_controlled_cells.csv", index=False)
    print(f"\nwrote 2 CSVs to {config.RESULTS}")


if __name__ == "__main__":
    import sys

    main(int(sys.argv[1]) if len(sys.argv) > 1
         else config.LENGTH_CONTROL_CLASS_CAP)
