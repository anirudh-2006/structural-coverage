"""E3's primary comparison: length-matched and restricted to common support,
on the tactic-STEP axis.

Decided in `notes/changes/2026-08-17-e3-design.md`, which set the order of
work as (1) recompute the instrument terms on the matched design, (2) settle
`redundancy_rate` (dropped), (3) run E3 on the matched design, (4) report the
excluded region as a result. This module is (3) and (4).

WHY IT HAD TO BE REDONE. Every "overlap region" figure in `paper/methods.md`
— the coverage stability check (0.0089 -> 0.0087), the `structural_breadth`
sign flip (-0.80 -> +0.04), the depth and Gini slice rows — comes from
`analysis.length_overlap`, whose `CHAR_OVERLAP = (400, 800)` is a single bin
on the CHARACTER axis. The 2026-08-17 length-axis correction established that
characters are the indefensible axis: the corpora overlap 0.215 on characters
and 0.856 on tactic steps, because mathlib source is hand-wrapped and carries
docstrings while a Goedel `full_proof` is generated. Those figures therefore
restrict to 15.5% of the human corpus and 14.3% of the machine corpus on an
axis the project has since rejected, while the design the paper says is
primary retains 99.8% and 75.9% on the axis it accepts.

TWO RESTRICTIONS, REPORTED SEPARATELY, BECAUSE THEY ANSWER DIFFERENT
OBJECTIONS.

  * **Common support** keeps every proof in a (class x step) cell where both
    corpora have usable mass. It answers "you standardized over cells one
    corpus barely occupies".
  * **1:1 matching** additionally draws one human declaration per machine
    proof from the same cell. It answers the objection common support does
    not: that the human vocabulary is measured over 70,086 proofs and the
    machine vocabulary over 29,750, and vocabulary size grows with corpus
    size. Under matching the two vocabularies are counted over the same
    number of proofs at the same class and length.

`vocabulary_rarefaction` answers the size objection a second way, without
matching, by measuring how the human vocabulary grows with corpus size.

All premise sets come from `analysis.proof_census` under its default
exclusion policy, i.e. with the one-sided contaminants of
`analysis.vocabulary_contamination` removed.
"""

from __future__ import annotations

import random

import pandas as pd

from src import config
from src.analysis import proof_census as pc
from src.analysis import tactic_strata as ts
from src.graph import load
from src.metrics import structural

RAREFACTION_REPEATS = 5
RAREFACTION_FRACTIONS = (0.05, 0.1, 0.25, 0.5, 0.75, 1.0)


def _bin_label(steps: int) -> str:
    for lo, hi in config.PROOF_STEP_BINS:
        if hi is None:
            if steps >= lo:
                return f"{lo}+"
        elif lo <= steps < hi:
            return f"{lo}-{hi}"
    return f"{config.PROOF_STEP_BINS[-1][0]}+"


def prepare(corpus: str) -> pd.DataFrame:
    """Census records with the cell key and the corrected premise set."""
    frame = pc.census(corpus).copy()
    frame["cls"] = frame["tactics"].map(lambda t: ts.assign_class(set(t)))
    frame["bin"] = frame["steps"].map(_bin_label)
    frame["cell"] = frame["cls"] + " x " + frame["bin"]
    frame["premise_set"] = pc.premise_sets(frame)
    return frame


# --- common support -------------------------------------------------------

def cell_table(human: pd.DataFrame, machine: pd.DataFrame,
               min_human: int = config.LENGTH_CELL_MIN_N) -> pd.DataFrame:
    """Per-cell mass on both sides, and whether the cell has common support."""
    h = human["cell"].value_counts()
    m = machine["cell"].value_counts()
    rows = []
    for cls, _ in ((c, None) for c in ts.ALL_CLASSES):
        for lo, hi in config.PROOF_STEP_BINS:
            label = f"{lo}+" if hi is None else f"{lo}-{hi}"
            cell = f"{cls} x {label}"
            hn, mn = int(h.get(cell, 0)), int(m.get(cell, 0))
            rows.append({
                "cell": cell, "class": cls, "bin": label,
                "human_n": hn, "machine_n": mn,
                "human_share": hn / len(human),
                "machine_share": mn / len(machine),
                "supported": hn >= min_human and mn > 0,
            })
    return pd.DataFrame(rows)


def restrict(frame: pd.DataFrame, cells: set[str]) -> pd.DataFrame:
    return frame[frame["cell"].isin(cells)]


def match(human: pd.DataFrame, machine: pd.DataFrame, cells: set[str],
          seed: int = config.RANDOM_SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One human declaration per machine proof, drawn within cell.

    Sampling is WITH replacement when a cell holds fewer human declarations
    than machine proofs, which happens in the thin `arith` cells. Drawing
    without replacement there would silently shrink the machine side back
    toward the human mass and undo the matching; drawing with replacement
    keeps the machine side whole and is reported as a per-cell reuse factor.
    """
    rng = random.Random(seed)
    by_cell = {c: list(idx) for c, idx in
               human[human["cell"].isin(cells)].groupby("cell").groups.items()}
    machine_kept = machine[machine["cell"].isin(cells)]
    picks = []
    for cell, n in machine_kept["cell"].value_counts().items():
        pool = by_cell[cell]
        picks.extend(rng.choices(pool, k=int(n)) if n > len(pool)
                     else rng.sample(pool, int(n)))
    return human.loc[picks], machine_kept


# --- metrics on a set of records -----------------------------------------

def summarise(frame: pd.DataFrame, label: str, g, communities, depths, layers
              ) -> dict:
    sets = list(frame["premise_set"])
    if not sets:
        return {"slice": label, "n": 0}
    breadth, breadth_step, depth_mean, sizes = [], [], [], []
    for steps, premises in zip(frame["steps"], sets):
        if not premises:
            continue
        breadth.append(structural.structural_breadth(premises, g, communities))
        breadth_step.append(structural.structural_breadth(
            premises, g, communities, length=max(int(steps), 1)))
        d = structural.depth_reach(premises, g, depths)
        if d["n"]:
            depth_mean.append(d["mean"])
        sizes.append(len(premises))
    vocab = {p for s in sets for p in s}
    cm = structural.centrality_mass(vocab, g, layers)
    return {
        "slice": label, "n": len(frame), "with_premises": len(sizes),
        "vocabulary": len(vocab),
        "premises_per_proof": _mean(sizes),
        "breadth_raw": _mean(breadth),
        "breadth_per_step": _mean(breadth_step),
        "depth_mean": _mean(depth_mean),
        "gini_mathematical": cm["mathematical"]["gini"],
        "gini_infrastructure": cm["infrastructure"]["gini"],
    }


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def coverage_row(human: pd.DataFrame, machine: pd.DataFrame, scope: str
                 ) -> dict:
    hv = {p for s in human["premise_set"] for p in s}
    mv = {p for s in machine["premise_set"] for p in s}
    cov = structural.coverage_overlap(mv, hv)
    return {"scope": scope, "human_proofs": len(human),
            "machine_proofs": len(machine),
            "human_vocab": len(hv), "machine_vocab": len(mv), **cov}


# --- rarefaction ----------------------------------------------------------

def vocabulary_rarefaction(frame: pd.DataFrame, corpus: str,
                           seed: int = config.RANDOM_SEED,
                           at_n: int | None = None) -> pd.DataFrame:
    """How the premise vocabulary grows with corpus size.

    The size objection to the primary result is that 70,086 human proofs
    should find more distinct premises than 29,750 machine proofs whatever
    the two populations are doing. This measures how much of the gap size
    alone can buy.
    """
    sets = list(frame["premise_set"])
    fractions = list(RAREFACTION_FRACTIONS)
    if at_n is not None and at_n < len(sets):
        # The comparison a reviewer actually wants: the human vocabulary
        # measured over exactly as many proofs as the machine corpus has.
        fractions = sorted({*fractions, at_n / len(sets)})
    rows = []
    for frac in fractions:
        n = max(1, round(frac * len(sets)))
        vocabs = []
        for rep in range(1 if frac == 1.0 else RAREFACTION_REPEATS):
            rng = random.Random(seed + rep)
            draw = sets if frac == 1.0 else rng.sample(sets, n)
            vocabs.append(len({p for s in draw for p in s}))
        rows.append({"corpus": corpus, "fraction": frac, "proofs": n,
                     "vocab_mean": _mean(vocabs),
                     "vocab_min": min(vocabs), "vocab_max": max(vocabs)})
    return pd.DataFrame(rows)


# --- entry point ----------------------------------------------------------

def main() -> None:
    human, machine = prepare("human"), prepare("machine")
    g = ts._explicit_graph()
    communities = structural.community_index(g)
    depths = structural.depth_index(g)
    layers = load.split_hub_layers(g)

    def fmt(x):
        return f"{x:.4f}"

    cells = cell_table(human, machine)
    supported = set(cells[cells["supported"]]["cell"])
    kept_h = cells[cells["supported"]]["human_share"].sum()
    kept_m = cells[cells["supported"]]["machine_share"].sum()

    print("=" * 78)
    print("COMMON SUPPORT — (tactic class x tactic-step bin), STEP axis")
    print("=" * 78)
    print(cells[(cells.human_n > 0) | (cells.machine_n > 0)].to_string(
        index=False, float_format=fmt))
    print(f"\nsupported cells {len(supported)} of {len(cells)}   "
          f"retains human {kept_h:.4f} (frozen "
          f"{config.H2_COMMON_SUPPORT_RETAINED_HUMAN}), machine {kept_m:.4f} "
          f"(frozen {config.H2_COMMON_SUPPORT_RETAINED_MACHINE})")

    excluded = cells[~cells["supported"] & (cells.machine_n > 0)]
    print("\nEXCLUDED REGION — reported as a result, not as attrition:")
    print(excluded[["cell", "human_n", "machine_n", "machine_share"]].to_string(
        index=False, float_format=fmt))

    h_supported = restrict(human, supported)
    m_supported = restrict(machine, supported)
    h_matched, m_matched = match(human, machine, supported)

    print()
    print("=" * 78)
    print("STRUCTURAL METRICS — full corpus, common support, matched")
    print("=" * 78)
    rows = [
        summarise(human, "human/full", g, communities, depths, layers),
        summarise(machine, "machine/full", g, communities, depths, layers),
        summarise(h_supported, "human/support", g, communities, depths, layers),
        summarise(m_supported, "machine/support", g, communities, depths, layers),
        summarise(h_matched, "human/matched", g, communities, depths, layers),
        summarise(m_matched, "machine/matched", g, communities, depths, layers),
    ]
    metrics = pd.DataFrame(rows)
    print(metrics.to_string(index=False, float_format=fmt))
    print("\ngaps (machine - human):")
    for scope in ("full", "support", "matched"):
        h = metrics[metrics["slice"] == f"human/{scope}"].iloc[0]
        m = metrics[metrics["slice"] == f"machine/{scope}"].iloc[0]
        print(f"  {scope:<9}" + "  ".join(
            f"{k} {m[k] - h[k]:+.4f}" for k in
            ("breadth_raw", "breadth_per_step", "depth_mean",
             "gini_mathematical")))

    print()
    print("=" * 78)
    print("COVERAGE — the primary result, on the step-axis designs")
    print("=" * 78)
    coverage = pd.DataFrame([
        coverage_row(human, machine, "full"),
        coverage_row(h_supported, m_supported, "common_support"),
        coverage_row(h_matched, m_matched, "matched_1to1"),
    ])
    print(coverage.to_string(index=False, float_format=fmt))

    print()
    print("=" * 78)
    print("RAREFACTION — how much of the vocabulary gap is corpus size?")
    print("=" * 78)
    rare = pd.concat(
        [vocabulary_rarefaction(human, "human", at_n=len(machine)),
         vocabulary_rarefaction(machine, "machine")],
        ignore_index=True)
    print(rare.to_string(index=False, float_format=fmt))

    config.RESULTS.mkdir(parents=True, exist_ok=True)
    cells.to_csv(config.RESULTS / "common_support_cells.csv", index=False)
    metrics.to_csv(config.RESULTS / "metrics_common_support.csv", index=False)
    coverage.to_csv(config.RESULTS / "coverage_common_support.csv", index=False)
    rare.to_csv(config.RESULTS / "vocabulary_rarefaction.csv", index=False)
    print(f"\nwrote 4 CSVs to {config.RESULTS}")


if __name__ == "__main__":
    main()
