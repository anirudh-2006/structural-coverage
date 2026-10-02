"""Does the length non-overlap threaten the H2 METRICS, not just D_m?

SUPERSEDED FOR EVERY "OVERLAP REGION" FIGURE, 2026-08-19. `CHAR_OVERLAP`
below is one bin on the CHARACTER axis, and the 2026-08-17 length-axis
correction rejected that axis (overlap coefficient 0.215 against 0.856 for
tactic steps). Its restricted rows keep 15.5% of the human corpus and 14.3%
of the machine corpus. `analysis.common_support` redoes them on the
(class x tactic-step) common-support design the E3 record calls primary,
which keeps 99.9% and 76.6%. THIS MODULE IS RETAINED DELIBERATELY: its
char-axis numbers are the sensitivity row, and deleting it would erase the
evidence that the axis choice matters. Do not quote its overlap rows as
results. See notes/changes/2026-08-19-common-support-step-axis.md.

`analysis.length_control` found that the two corpora barely overlap in
declaration length -- 77.7% of human declarations under 400 characters,
85.3% of machine proofs over 800 -- and that length-controlling the recall
instrument artifact removed it entirely. Direct standardization does not
flag extrapolation; it just reweights. So the same objection lands on every
length-controlled comparison in the paper, not only on the instrument
reference line.

This module answers two questions BEFORE E3 runs:

  1. How much mass is actually in the overlap region, and what do the
     structural metrics look like restricted to it?
  2. Does the non-overlap survive a WRAP-INVARIANT length measure? Human
     length is mathlib source -- hand-wrapped near 100 columns, carrying
     docstrings -- while machine length is a generated `full_proof`. If the
     non-overlap were a formatting artifact, every length-controlled number
     would be measuring the wrong thing. Tactic-invocation count, matched
     vocabulary and matched matcher on both sides, is the check.

A NOTE ON COST, which changes the design. The human side is not the
495-declaration audit sample; it is every eligible mathlib tactic proof with
a locatable block -- 70,086 of them. A length-MATCHED subsample is therefore
cheap on the human side: even a thin machine length stratum has thousands of
human declarations to draw against. The expensive direction is the machine
side, which has 29,750 proofs total. This is why matching is affordable as a
primary analysis rather than a robustness afterthought.

CLAUDE.md §6 NOTE. Running the structural metrics against the machine corpus
is E3 in substance. Once these numbers exist the metric definitions are
frozen in practice, and `redundancy_rate` -- still unimplemented -- can no
longer be defined blind. That is stated in `metrics.structural` and is a
decision for the author, not a coding gap.
"""

from __future__ import annotations

import collections
import itertools
import random
from dataclasses import dataclass, field

import pandas as pd

from src import config
from src.analysis import tactic_strata as ts
from src.analysis.automation_confound import GOEDEL_PARQUET
from src.analysis.spurious_symmetry import _theorem_name, machine_declaration_block
from src.extract import audit, decl_source
from src.extract import source as src_mod
from src.graph import load
from src.metrics import structural

# Overlap region on the character axis: the one bin of PROOF_LENGTH_BINS with
# comparable mass on both sides (human 0.155, machine 0.143). Fixed from the
# 2026-08-16 length-control table, not tuned here.
CHAR_OVERLAP = (400, 800)


@dataclass
class ProofRecord:
    """One proof, either corpus, seen through one instrument."""

    corpus: str
    name: str
    chars: int
    steps: int
    premises: frozenset[str] = field(default_factory=frozenset)


# --- corpora --------------------------------------------------------------

def human_records(limit: int | None = None, seed: int = config.RANDOM_SEED
                  ) -> list[ProofRecord]:
    """Every eligible mathlib tactic proof with a locatable block.

    `limit` draws a seeded subsample for iteration speed; the default is the
    full census, which is the point -- the human side is 70,086 proofs, not
    the audit's 495.
    """
    g = ts._explicit_graph()
    known = frozenset(load.declaration_names(g))
    _, block_index, _ = ts._human_census()

    names = sorted(block_index)
    if limit is not None and limit < len(names):
        names = sorted(random.Random(seed).sample(names, limit))

    out = []
    for name in names:
        block = block_index[name]
        text = src_mod.read_module_source(g.nodes[name]["file_module"])
        found = audit.extract(block, known, decl_name=name, file_text=text)
        out.append(ProofRecord(
            corpus="human", name=name, chars=len(block),
            steps=audit.tactic_steps(decl_source.proof_body(block)),
            premises=found.resolved,
        ))
    return out


def machine_records(limit: int | None = None, seed: int = config.RANDOM_SEED
                    ) -> list[ProofRecord]:
    """Goedel proofs at declaration scope, corpus header excluded."""
    g = ts._explicit_graph()
    known = frozenset(load.declaration_names(g))
    df = pd.read_parquet(GOEDEL_PARQUET)

    idx = list(range(len(df)))
    if limit is not None and limit < len(idx):
        idx = sorted(random.Random(seed).sample(idx, limit))

    out = []
    for i in idx:
        row = df.iloc[i]
        block = machine_declaration_block(row["full_proof"])
        if block is None:
            continue
        # decl_name must be non-empty or `audit.extract` skips prefix
        # resolution entirely — including the corpus header's `open` lines,
        # which are the machine side's only prefix source. Same call shape as
        # spurious_symmetry, so the two analyses see the same premise sets.
        found = audit.extract(
            block, known, decl_name=_theorem_name(block),
            file_text=row["full_proof"])
        out.append(ProofRecord(
            corpus="machine", name=str(row["problem_id"]), chars=len(block),
            steps=audit.tactic_steps(decl_source.proof_body(block)),
            premises=found.resolved,
        ))
    return out


# --- overlap ---------------------------------------------------------------

def overlap_table(
    human: list[ProofRecord], machine: list[ProofRecord],
    axis: str, edges: tuple[int, ...],
) -> pd.DataFrame:
    """Share of each corpus per bin, plus the overlapping mass per bin."""
    def binned(recs):
        counts = collections.Counter()
        for r in recs:
            v = getattr(r, axis)
            lab = f"{edges[-1]}+"
            for lo, hi in itertools.pairwise(edges):
                if lo <= v < hi:
                    lab = f"{lo}-{hi}"
                    break
            counts[lab] += 1
        return {k: v / len(recs) for k, v in counts.items()}

    h, m = binned(human), binned(machine)
    labels = ([f"{lo}-{hi}" for lo, hi in itertools.pairwise(edges)]
              + [f"{edges[-1]}+"])
    rows = []
    for lab in labels:
        hv, mv = h.get(lab, 0.0), m.get(lab, 0.0)
        rows.append({"axis": axis, "bin": lab, "human": hv, "machine": mv,
                     "overlap_mass": min(hv, mv)})
    return pd.DataFrame(rows)


def overlap_coefficient(frame: pd.DataFrame) -> float:
    """Sum of per-bin min(human, machine). 1.0 = identical, 0 = disjoint."""
    return float(frame["overlap_mass"].sum())


# --- metrics on a slice ---------------------------------------------------

def metric_summary(
    recs: list[ProofRecord], g, communities, depths, layers, label: str,
) -> dict:
    """Structural metrics over a set of proofs, per-proof means."""
    if not recs:
        return {"slice": label, "n": 0}
    breadth_raw, breadth_dens, depth_mean, depth_max, sizes = [], [], [], [], []
    for r in recs:
        if not r.premises:
            continue
        breadth_raw.append(structural.structural_breadth(
            r.premises, g, communities))
        breadth_dens.append(structural.structural_breadth(
            r.premises, g, communities, length=max(r.steps, 1)))
        d = structural.depth_reach(r.premises, g, depths)
        if d["n"]:
            depth_mean.append(d["mean"])
            depth_max.append(d["max"])
        sizes.append(len(r.premises))
    cm = structural.centrality_mass(
        {p for r in recs for p in r.premises}, g, layers)
    return {
        "slice": label, "n": len(recs),
        "with_premises": len(sizes),
        "premises_per_proof": _mean(sizes),
        "breadth_raw": _mean(breadth_raw),
        "breadth_per_step": _mean(breadth_dens),
        "depth_mean": _mean(depth_mean),
        "depth_max": _mean(depth_max),
        "gini_mathematical": cm["mathematical"]["gini"],
        "gini_infrastructure": cm["infrastructure"]["gini"],
    }


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def _slice(recs, axis, lo, hi):
    return [r for r in recs if lo <= getattr(r, axis) < hi]


# --- entry point ----------------------------------------------------------

def main(human_limit: int | None = None, machine_limit: int | None = None
         ) -> None:
    g = ts._explicit_graph()
    communities = structural.community_index(g)
    depths = structural.depth_index(g)
    layers = load.split_hub_layers(g)

    human = human_records(human_limit)
    machine = machine_records(machine_limit)
    print(f"human {len(human):,} proofs   machine {len(machine):,} proofs")

    char_edges = tuple(lo for lo, _ in config.PROOF_LENGTH_BINS)
    step_edges = (0, 2, 4, 8, 16, 32)

    frames = []
    for axis, edges in (("chars", char_edges), ("steps", step_edges)):
        print()
        print("=" * 78)
        print(f"LENGTH OVERLAP on {axis.upper()}")
        print("=" * 78)
        f = overlap_table(human, machine, axis, edges)
        frames.append(f)
        print(f.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
        print(f"\noverlap coefficient = {overlap_coefficient(f):.4f}   "
              "(1.0 identical, 0 disjoint)")

    print()
    print("=" * 78)
    print("TASK 3 VERDICT — does the non-overlap survive a structural measure?")
    print("=" * 78)
    hs = sorted(r.steps for r in human)
    ms = sorted(r.steps for r in machine)
    for label, xs in (("human", hs), ("machine", ms)):
        q = [xs[int(p * (len(xs) - 1))] for p in (0.1, 0.25, 0.5, 0.75, 0.9)]
        print(f"  {label:<8} tactic steps  p10={q[0]}  p25={q[1]}  "
              f"median={q[2]}  p75={q[3]}  p90={q[4]}")
    print(f"  char overlap coefficient  = {overlap_coefficient(frames[0]):.4f}")
    print(f"  step overlap coefficient  = {overlap_coefficient(frames[1]):.4f}")

    print()
    print("=" * 78)
    print("METRICS — full corpus vs the CHARACTER overlap region "
          f"[{CHAR_OVERLAP[0]}, {CHAR_OVERLAP[1]})")
    print("=" * 78)
    rows = [
        metric_summary(human, g, communities, depths, layers, "human/full"),
        metric_summary(machine, g, communities, depths, layers, "machine/full"),
        metric_summary(_slice(human, "chars", *CHAR_OVERLAP),
                       g, communities, depths, layers, "human/overlap"),
        metric_summary(_slice(machine, "chars", *CHAR_OVERLAP),
                       g, communities, depths, layers, "machine/overlap"),
    ]
    summary = pd.DataFrame(rows)
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    print()
    print("gaps (machine - human):")
    for scope in ("full", "overlap"):
        h = summary[summary["slice"] == f"human/{scope}"].iloc[0]
        m = summary[summary["slice"] == f"machine/{scope}"].iloc[0]
        print(f"  {scope:<9}"
              + "  ".join(
                  f"{k} {m[k] - h[k]:+.4f}"
                  for k in ("breadth_raw", "breadth_per_step", "depth_mean",
                            "gini_mathematical")))

    print()
    print("=" * 78)
    print("COVERAGE OVERLAP — corpus-level premise vocabularies")
    print("=" * 78)
    cov_rows = []
    for scope, hsel, msel in (
        ("full", human, machine),
        ("overlap", _slice(human, "chars", *CHAR_OVERLAP),
         _slice(machine, "chars", *CHAR_OVERLAP)),
    ):
        hv = {p for r in hsel for p in r.premises}
        mv = {p for r in msel for p in r.premises}
        cov = structural.coverage_overlap(mv, hv)
        # Labelled at write time, not annotated afterwards: these rows are
        # doubly superseded -- uncorrected premise sets (the exclusions of
        # `proof_census.premise_sets` are not applied here) AND the character
        # axis. Regeneration must keep the label or the CSV starts asserting
        # 118,514 / 0.0089 / 99.1% as current again.
        cov_rows.append({"scope": scope, "human_vocab": len(hv),
                         "machine_vocab": len(mv), **cov,
                         "premise_set_basis": "raw_uncorrected",
                         "length_axis": "characters",
                         "superseded_by":
                             "results/coverage_common_support.csv"})
        print(f"  {scope:<9} human vocab {len(hv):>7,}  machine vocab "
              f"{len(mv):>7,}  jaccard {cov['jaccard']:.4f}  "
              f"human-only {cov['human_only']:>7,} "
              f"({cov['human_only_fraction']:.3f})")

    _write(frames, summary, pd.DataFrame(cov_rows))


def _write(frames, summary, cov) -> None:
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_csv(
        config.RESULTS / "length_overlap.csv", index=False)
    summary.to_csv(
        config.RESULTS / "metrics_by_length_slice.csv", index=False)
    cov.to_csv(config.RESULTS / "coverage_overlap_by_slice.csv", index=False)
    print(f"\nwrote 3 CSVs to {config.RESULTS}")


if __name__ == "__main__":
    import sys

    a = [int(x) if x != "all" else None for x in sys.argv[1:]]
    main(*(a or [None, None]))
