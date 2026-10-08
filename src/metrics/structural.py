"""The structural coverage metrics — the paper's constructive core.

FOUR metrics, not five. `redundancy_rate` was scope-frozen out of the paper
on 2026-08-17; see its tombstone below.

MEASURED STATUS, keyed to the hypotheses of CLAUDE.md §3:

  * `coverage_overlap`  -- H2a, the PRIMARY result. A direct count needing no
                           standardization, no length control and no
                           imputation, which is the only thing in the analysis
                           that can be said of. RUN on both corpora.
  * `depth_reach`       -- WITHDRAWN 2026-09-04, supports no claim. The
                           published `dag_layer` it reads is a centrality
                           proxy, not distance from primitives. See its
                           docstring and 2026-09-04-depth-withdrawn.md.
  * `structural_breadth`-- secondary. Sign stable on the tactic-step axis,
                           magnitude design-dependent by 4x. RUN on both
                           corpora.
  * `centrality_mass`   -- RUN on both corpora, at all three scopes, layers
                           kept separate throughout. Not a headline result.

The original H2 -- "machine proofs draw premises from a structurally narrower
and more centrally concentrated region" -- is SPLIT. Narrower in vocabulary:
yes, decisively (`coverage_overlap`). The depth half is not adjudicated either
way: the metric that was to answer it is withdrawn, because `dag_layer` does
not measure what its name and the release's documentation say.

FROZEN once machine-corpus results exist (CLAUDE.md §6). Implemented and
exercised on human proofs first, committed, THEN pointed at machine corpora.

Every metric takes a length control, and LENGTH MEANS TACTIC STEPS, not
characters (2026-08-17 length-axis correction: the corpora overlap 0.856 on
steps against 0.215 on characters, so the character axis is substantially a
formatting control). Short proofs mechanically use fewer and more common
premises; uncontrolled length is the obvious reviewer objection, and the
2026-08-16 length-control result showed it is not a theoretical one.

`coverage_overlap` is the exception and that is why it leads: a count of
distinct premises does not depend on the length distribution it was collected
over, and it moves 0.0129 -> 0.0128 under the restriction that reverses or
destroys every other comparison here.

TWO THINGS ARE DELIBERATELY NOT REBUILT HERE. `dag_layer` and `in_degree`
come from the published MathlibGraph release, per CLAUDE.md §4: we extend
their baseline, we do not re-derive it. NOTE that not re-deriving is why the
`dag_layer` inversion went unnoticed for three weeks -- we read the column
as distance from primitives and it behaves as a centrality proxy; see
`depth_reach`. Louvain communities are computed, because the release does not
carry a community assignment, and they are cached so the partition is
identical across every figure in the paper.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import networkx as nx
import pandas as pd

from src import config
from src.graph import load

log = logging.getLogger(__name__)

_COMMUNITY_CACHE = config.MATHLIB_GRAPH_DIR / "_cache_louvain_communities.parquet"

# `dag_layer == -1` marks declarations the release could not place — nodes in
# a cycle, or with a dangling dependency. 5,732 of 308,129 (1.9%). They are
# EXCLUDED rather than coerced to 0, which would pull every mean toward the
# uncited-leaf end of the scale. (A further 36,788 nodes carry a silently
# truncated value that is NOT marked -1 and cannot be excluded this way.)
UNPLACED_LAYER = -1


# --- shared graph-derived tables -----------------------------------------

def depth_index(g: nx.DiGraph) -> dict[str, int]:
    """Published `dag_layer` per declaration, as released. Not recomputed.

    NOT distance from primitives as we had read it
    -- it correlates +0.677 with log in-degree and its top layer is `Eq.refl`.
    See `depth_reach` for the audit and the withdrawal.
    """
    return {
        n: a["dag_layer"]
        for n, a in g.nodes(data=True)
        if a.get("dag_layer", UNPLACED_LAYER) != UNPLACED_LAYER
    }


def community_index(g: nx.DiGraph, force: bool = False) -> dict[str, int]:
    """Louvain community per declaration, computed once and cached.

    Undirected projection: Louvain is defined on undirected graphs, and a
    dependency's direction does not change which region of the library it
    belongs to. Seeded from config so the partition is reproducible; cached
    so every figure in the paper uses the SAME partition, which matters
    because community labels are not stable across runs.
    """
    if not force and _COMMUNITY_CACHE.exists():
        df = pd.read_parquet(_COMMUNITY_CACHE)
        return dict(zip(df["name"], df["community"]))

    log.info("computing Louvain communities (not cached) — this is slow")
    communities = nx.community.louvain_communities(
        g.to_undirected(as_view=False),
        resolution=config.LOUVAIN_RESOLUTION,
        seed=config.LOUVAIN_SEED,
    )
    index = {n: i for i, comm in enumerate(communities) for n in comm}
    _COMMUNITY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {"name": list(index), "community": [index[n] for n in index]}
    ).to_parquet(_COMMUNITY_CACHE, index=False)
    return index


def gini(values: Sequence[float]) -> float:
    """Standard Gini on non-negative values. 0 = flat, ->1 = concentrated."""
    xs = sorted(float(v) for v in values)
    n = len(xs)
    if n == 0:
        return float("nan")
    total = sum(xs)
    if total <= 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return (2 * cum) / (n * total) - (n + 1) / n


# --- the metrics ----------------------------------------------------------

def centrality_mass(
    premises: set[str],
    g: nx.DiGraph,
    layers: tuple[set[str], set[str]] | None = None,
) -> dict:
    """In-degree distribution over premises used, as deciles + Gini.

    RETURNS THE TWO HUB LAYERS SEPARATELY AND NEVER AGGREGATES THEM. Li et
    al.'s Finding 3: centrality measures technical utility, not mathematical
    depth — `Eq.refl` is 2nd by in-degree, the Chinese Remainder Theorem is
    not in the top 100. An aggregate Gini over both layers mixes "how much
    language plumbing did this proof touch" with "how central are its
    mathematical premises", which is uninterpretable. CLAUDE.md §4.

    RUN STATUS: run on BOTH corpora, at all three scopes of the common-support
    design (results/metrics_common_support.csv, results/metrics_by_length_slice.csv),
    with the layers kept separate throughout. `gini_mathematical` is +0.013
    machine-over-human and does not move across full corpora, common support
    or 1:1 matching. It is not a headline result and is not promoted to one:
    per Li et al.'s Finding 3 a centrality difference this size supports no
    claim about mathematical depth in either direction.
    """
    infrastructure, mathematical = layers or load.split_hub_layers(g)
    out: dict = {}
    for label, members in (("infrastructure", infrastructure),
                           ("mathematical", mathematical)):
        sel = [g.nodes[p]["in_degree"] for p in premises
               if p in members and p in g]
        out[label] = {
            "n": len(sel),
            "gini": gini(sel) if sel else float("nan"),
            "mean_in_degree": (sum(sel) / len(sel)) if sel else float("nan"),
            "deciles": (
                list(pd.Series(sel).quantile(
                    [i / config.CENTRALITY_DECILES
                     for i in range(1, config.CENTRALITY_DECILES)]
                ))
                if sel else []
            ),
        }
    return out


def structural_breadth(
    premises: set[str],
    g: nx.DiGraph,
    communities: dict[str, int] | None = None,
    length: float | None = None,
) -> float:
    """Distinct Louvain communities touched, optionally per unit length.

    SECONDARY. SIGN STABLE, MAGNITUDE DESIGN-DEPENDENT BY 4x. On the
    tactic-step axis the per-step gap (machine - human) is negative at every
    scope and never flips:

        full corpora  -0.607     common support  -0.780     matched 1:1  -0.201

    QUOTE ALL THREE, NEVER ONE ALONE, and do not pick whichever magnitude is
    convenient. The matched value is 3-4x smaller than the unmatched one, so
    how much breadth differs is a property of the design as much as of the
    corpora; that the direction does not move is the part that is safe to
    assert.

    A PREVIOUSLY REPORTED SIGN FLIP (-0.80 full corpus -> +0.04 overlap
    region) WAS A CHARACTER-AXIS ARTIFACT and must not be repeated -- the
    overlap region it came from was cut on the character axis this project
    rejected on 2026-08-17 and retained only 14.3% of the machine corpus. See
    notes/changes/2026-08-19-common-support-step-axis.md.

    STANDING LIMITATION: the Louvain partition is degenerate for this purpose.
    Median community size is 1, 24,437 of 24,643 communities have <= 3
    members, and the five largest hold 68% of the graph. Breadth is a coarse
    measure and is reported as one.

    `length` is the proof's length control, in TACTIC STEPS, not characters.
    Passing None returns the RAW count, which is the quantity to compare
    within a length stratum; passing a length returns the density, which is
    what a pooled comparison needs. Both are reported — a raw count is not
    comparable across corpora whose length distributions barely overlap.
    """
    idx = communities if communities is not None else community_index(g)
    touched = {idx[p] for p in premises if p in idx}
    if length is None:
        return float(len(touched))
    return len(touched) / length if length else float("nan")


def depth_reach(
    premises: set[str],
    g: nx.DiGraph,
    depths: dict[str, int] | None = None,
) -> dict:
    """Mean and max `dag_layer` over premises used. NOT a depth measure.

    WITHDRAWN 2026-09-04. THIS METRIC SUPPORTS NO CLAIM IN THE PAPER.
    Do not quote +23.64, +19.26, +18.39, or the 3.2% namespace-matched null
    from this function or from anything downstream of it. It is retained as
    running code because the withdrawal record and the negative methodological
    finding (methods M4, limitations L5) refer to what it computes.

    WHY. This docstring described `dag_layer` as distance from primitive
    axioms, which is how the graph release documents it. The 2026-08-23 audit
    (notes/changes/2026-08-23-depth-definition-audit.md) established that the
    column runs BACKWARDS:

      * layer 0 holds 119,633 nodes whose maximum in_degree is 0 — uncited
        leaves, not axioms;
      * the highest layer (83) holds Eq.refl (69,580 citations), Set, LE.le,
        Eq.mpr, DFunLike.coe;
      * corr(dag_layer, log1p(in_degree)) = +0.677;
      * 42,520 nodes (13.8%) are silently truncated, 36,788 of them carrying a
        partial value indistinguishable from a completed one.

    High `dag_layer` therefore means heavily-cited foundational
    infrastructure, low means uncited leaf. The quantity is a CENTRALITY PROXY,
    not derivation length, so a gap in it cannot carry a depth claim — that is
    exactly the inference Li et al.'s Finding 3 rules out, and this is a second
    instance of it on a different structural quantity.

    WHY WITHDRAWN RATHER THAN REINTERPRETED. Read correctly the gap says
    machine proofs concentrate on more heavily-cited infrastructure, which
    points the same way as coverage. Re-pointing a metric at a new claim after
    its comparison has been seen is a researcher degree of freedom under
    CLAUDE.md §6, whatever its independent merits. If someone proposes it,
    say so.

    The figures this docstring carried, and their correction history, are in
    notes/changes/2026-09-04-depth-withdrawn.md. They are not repeated here.

    HISTORY, kept short because none of it is a live claim. The metric was
    promoted when centrality was demoted (2026-08-12), reported as a
    counter-finding, and defended with two pre-registered mechanism tests --
    a namespace-matched null and an automation-emission split
    (notes/changes/2026-08-17-depth-mechanism.md,
    2026-08-23-automation-depth.md). Both are void: they tested mechanisms for
    a gap in a quantity that is not what the metric assumed it was. The
    namespace null additionally dropped 239 of 1,118 machine premises (21.4%)
    as unmatchable, all root-level, under a singleton-region convention
    (2026-09-04 verification pass).

    Declarations the release could not place (`dag_layer == -1`) are excluded
    and counted, never coerced to 0.
    """
    idx = depths if depths is not None else depth_index(g)
    vals = [idx[p] for p in premises if p in idx]
    unplaced = sum(1 for p in premises if p in g and p not in idx)
    if not vals:
        return {"mean": float("nan"), "max": float("nan"),
                "n": 0, "unplaced": unplaced}
    return {
        "mean": sum(vals) / len(vals),
        "max": max(vals),
        "n": len(vals),
        "unplaced": unplaced,
    }


def redundancy_rate(proof_steps: list[str], g: nx.DiGraph) -> float:
    """SCOPE-FROZEN 2026-08-17. Out of the paper, not unimplemented.

    Decided by the author on 2026-08-17 and recorded in
    notes/changes/2026-08-17-redundancy-rate-dropped.md. Four metrics for four
    pages.

    The reason it is DROPPED rather than deferred: by the time it would have
    been written, machine-side results existed for the other four metrics
    (analysis.length_overlap), so its definition could no longer be fixed
    blind. CLAUDE.md §6 makes that a researcher-degrees-of-freedom problem, not
    a scheduling one, and it was already flagged from the start as the most
    reviewer-attackable metric and a demote-to-secondary candidate. Defining it
    under that constraint would invite exactly the objection the paper exists
    to pre-empt.

    WHAT IS LOST, and it is a real loss rather than a costless tidy-up: this
    was the ONLY metric over proof STEPS rather than premise SETS. Nothing
    else in the paper measures whether a proof rebuilds something the library
    already contains, which is the most direct operationalisation of
    "idiomatic" the project had. Dropping it is also what killed H5
    (CLAUDE.md §3), which depended on it. THIS GOES IN FUTURE WORK -- stated
    as a gap, not papered over. Two things partially cover it and neither is a
    substitute: coverage overlap bounds how much library the machine corpus
    could be reusing at all (1,127 of 308,129 declarations), and `arith` x 0-2
    steps being 23.1% of that corpus says a quarter of those proofs are a
    single solver call, which neither reuses nor re-derives library results in
    any interesting sense.

    This function is retained as a tombstone so the decision is visible where
    someone would look for the metric, rather than only in the log. Do not
    implement it. Reintroducing it after Sep 4 is a scope violation regardless
    of how it is defined.
    """
    raise NotImplementedError(
        "redundancy_rate is scope-frozen — see change record, not a bug "
        "(notes/changes/2026-08-17-redundancy-rate-dropped.md)."
    )


def coverage_overlap(machine: set[str], human: set[str]) -> dict:
    """Jaccard overlap, plus the size of the human-only region. H2a, PRIMARY.

    THIS IS THE PAPER'S MAIN RESULT (CLAUDE.md §3, H2a). Measured on both
    corpora under the corrected exclusion policy of
    notes/changes/2026-08-19-vocabulary-contamination.md:

        human vocabulary   78,642      machine vocabulary   1,127
        Jaccard            0.0129      human-only           0.9871

    The human-only region is the paper's point: two proof sets can be equally
    correct while one never touches a region of the library the other lives
    in. Reported as a count AND as a fraction of the human set, because the
    two corpora do not have the same premise-set size.

    IT NEEDS NO LENGTH CONTROL AND NO STANDARDIZATION, and that is why it
    leads rather than depth or breadth. A count of distinct premises does not
    depend on the length distribution it was collected over: Jaccard moves
    0.0129 -> 0.0128 under the common-support restriction that reverses or
    destroys every other comparison in this module. The gap is two orders of
    magnitude; the measured instrument reference line is 0.113 in
    premise-fraction units, far too small to manufacture it, and under-recovery
    is directional -- premises we miss cannot ADD to the machine vocabulary.

    Do NOT quote the uncorrected 118,514 / 0.0089 / 0.9911. Those figures were
    inflated on the human side only, by 33.6%, by two one-sided extractor
    artifacts (the declaration's own name, and the `lemma` keyword). They are
    reported in the paper as the uncorrected row and nowhere else.

    Corpus size buys almost none of the gap, and this is measured rather than
    argued: rarefied to the machine corpus's own size the human vocabulary is
    still 49,601 (44x), and the 1:1 class-and-step-matched design gives 21,162
    against 1,123 (18.8x, 96.3% human-only).
    """
    inter = machine & human
    union = machine | human
    human_only = human - machine
    machine_only = machine - human
    return {
        "jaccard": len(inter) / len(union) if union else float("nan"),
        "intersection": len(inter),
        "human_only": len(human_only),
        "machine_only": len(machine_only),
        "human_only_fraction": len(human_only) / len(human) if human else float("nan"),
        "machine_only_fraction": (
            len(machine_only) / len(machine) if machine else float("nan")
        ),
    }
