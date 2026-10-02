"""Is `depth_reach` measuring proof behaviour, or mathlib's construction?

WITHDRAWN 2026-09-04 — THIS MODULE SUPPORTS NO CLAIM IN THE PAPER. It tests
a mechanism for a gap in `dag_layer`, which the 2026-08-23 audit showed is a
centrality proxy, not distance from primitives. The depth finding is withdrawn
(notes/changes/2026-09-04-depth-withdrawn.md); everything below is retained as
the record of how it was investigated, not as a live result. Do not quote its
figures.

`depth_reach` runs OPPOSITE to H2's stated direction: machine premises are
deeper by +32.9 on the full corpus and +25.1 in the overlap region. The metric
docstring says "Hypothesis: human proofs reach deeper." They do not.

Two readings, and the test that separates them (pre-registered in
notes/changes/2026-08-17-depth-mechanism-prediction.md):

  A behavioural  machine proofs really do invoke results further from the
                 primitives. depth_reach works; H2's wording is wrong.
  B topological  machine premises are deep because of WHERE IN MATHLIB THEY
                 LIVE. Competition statements live over `Real`, `Nat`,
                 `Finset` and the ordered-field hierarchy, and lemmas there
                 sit far from the primitives because the algebraic hierarchy
                 beneath them is long. Then depth_reach measures which region
                 a problem forces you into, and cannot carry H2, because H2 is
                 about proof behaviour and this would be about mathlib.

The discriminating test is a REGION-MATCHED null. Comparing the machine
vocabulary against random human premises tests only whether it is unusual for
a set of that size (N1, the weak null). Comparing it against human premises
drawn from the SAME library regions in the SAME proportions tests whether the
depth survives once topology is held fixed (N2).

Type-level and usage-weighted versions are both computed: the observed +25.1
is usage-weighted, the vocabulary comparison is type-level, and they can come
apart.

WHY REGION = NAMESPACE, NOT LOUVAIN COMMUNITY. The cached Louvain partition is
degenerate for matching: median community size is 1, 24,437 of its 24,643
communities have 3 or fewer members (8.1% of nodes), and the five largest hold
68% of the graph. Matching within it is therefore matching to one of ~5 giant
blobs, i.e. barely matching at all -- an early version of this module did
exactly that and produced a null indistinguishable from the unmatched one.
Top-level namespace (`Nat`, `Real`, `Finset`, ...) is coarser in principle but
actually partitions: it is what "competition-arithmetic lemmas sit deep in the
DAG" is a claim about, and it is human-legible in the paper. Louvain is
retained as a reported cross-check with its degeneracy stated.
"""

from __future__ import annotations

import collections
import random

import pandas as pd

from src import config
from src.analysis import length_overlap as lo
from src.analysis import tactic_strata as ts
from src.extract import audit, ceiling
from src.extract import source as src_mod
from src.graph import load
from src.metrics import structural

RESAMPLES = 2_000


def _region_namespace(name: str) -> str:
    """Top-level namespace: the human-legible cross-check on Louvain."""
    return name.split(".", 1)[0] if "." in name else name


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def null_unmatched(
    human_pool: list[str], depths: dict[str, int], size: int,
    resamples: int = RESAMPLES, seed: int = config.RANDOM_SEED,
) -> list[float]:
    """N1: random size-matched subsets of the human vocabulary."""
    rng = random.Random(seed)
    pool = [p for p in human_pool if p in depths]
    return [
        _mean(depths[p] for p in rng.sample(pool, min(size, len(pool))))
        for _ in range(resamples)
    ]


def null_region_matched(
    human_pool: list[str], depths: dict[str, int], regions: dict,
    machine_vocab: list[str], resamples: int = RESAMPLES,
    seed: int = config.RANDOM_SEED,
) -> tuple[list[float], float, int]:
    """N2: draws reproducing the machine vocabulary's region distribution.

    For each machine premise, draw a human premise from the SAME region. A
    region with no human premises other than the machine ones themselves
    cannot be matched and is skipped; the count is returned, because a large
    unmatchable share would itself be the finding.

    Human premises that are also in the machine vocabulary are excluded from
    the pool, so the null cannot be satisfied by redrawing the very premises
    under test.
    """
    machine_set = set(machine_vocab)
    by_region: dict[int, list[str]] = collections.defaultdict(list)
    for p in human_pool:
        if p in depths and p in regions and p not in machine_set:
            by_region[regions[p]].append(p)

    targets, unmatched = [], 0
    for p in machine_vocab:
        r = regions.get(p)
        if r is None or not by_region.get(r):
            unmatched += 1
            continue
        targets.append(r)

    rng = random.Random(seed)
    out = []
    for _ in range(resamples):
        vals = [depths[rng.choice(by_region[r])] for r in targets]
        out.append(_mean(vals))
    return out, len(targets) / len(machine_vocab) if machine_vocab else 0.0, unmatched


def _pval(observed: float, null: list[float]) -> float:
    """Two-sided empirical p, with the standard +1 correction."""
    n = len(null)
    above = sum(1 for x in null if x >= observed)
    below = sum(1 for x in null if x <= observed)
    return min(1.0, 2 * (min(above, below) + 1) / (n + 1))


def _interval(null: list[float]) -> tuple[float, float]:
    s = sorted(null)
    return s[int(0.025 * len(s))], s[min(len(s) - 1, int(0.975 * len(s)))]


def instrument_depth_bias(cap: int = 2_500) -> pd.DataFrame:
    """Is the extractor's blind spot DEPTH-CORRELATED? Human side, ground truth.

    The pre-registration named this as the alternative mechanical explanation
    and did not test it. It matters: the residual we miss is dominated by
    simp-set lemmas (`le_refl`, `mul_one`, `Nat.cast_one`) and notation-backed
    definitions (`setOf`, `Top.top`, `Set.iUnion`), and those are SHALLOW. If
    we systematically drop shallow premises, measured depth is inflated on
    both sides -- and inflated MORE on the machine side, whose miss rate is
    higher by D_m = +0.099.

    Human declarations have ground truth: the explicit subgraph says which
    targets exist, and the extractor says which it recovered. So the depth of
    RECOVERED versus MISSED targets is directly measurable.
    """
    g = ts._explicit_graph()
    depths = structural.depth_index(g)
    _, mathematical = load.split_hub_layers(g)
    known = frozenset(load.declaration_names(g))
    _, block_index, _ = ts._human_census()

    names = sorted(block_index)
    rng = random.Random(config.RANDOM_SEED)
    if cap < len(names):
        names = sorted(rng.sample(names, cap))

    rec_d, miss_d = [], []
    for name in names:
        block = block_index[name]
        text = src_mod.read_module_source(g.nodes[name]["file_module"])
        found = audit.extract(block, known, decl_name=name, file_text=text)
        for target in g.successors(name):
            if target not in mathematical or target not in depths:
                continue
            hit = (target in found.resolved
                   or ceiling.last_component(target) in found.suffix_tokens)
            (rec_d if hit else miss_d).append(depths[target])

    return pd.DataFrame([{
        "recovered_n": len(rec_d), "recovered_mean_depth": _mean(rec_d),
        "missed_n": len(miss_d), "missed_mean_depth": _mean(miss_d),
        "bias": _mean(rec_d) - _mean(miss_d),
        "declarations": len(names),
    }])


def main(human_limit: int | None = None, machine_limit: int | None = None) -> None:
    g = ts._explicit_graph()
    depths = structural.depth_index(g)
    communities = structural.community_index(g)
    namespaces = {n: _region_namespace(n) for n in g.nodes}

    human = lo.human_records(human_limit)
    machine = lo.machine_records(machine_limit)

    # Type level: the vocabularies.
    h_vocab = sorted({p for r in human for p in r.premises})
    m_vocab = sorted({p for r in machine for p in r.premises})
    # Usage level: every occurrence, so a premise used 500 times counts 500x.
    h_uses = [p for r in human for p in r.premises]
    m_uses = [p for r in machine for p in r.premises]

    print(f"human vocab {len(h_vocab):,}   machine vocab {len(m_vocab):,}")
    print(f"human uses  {len(h_uses):,}   machine uses  {len(m_uses):,}")

    rows = []
    for level, h_set, m_set in (
        ("type", h_vocab, m_vocab),
        ("usage", h_uses, m_uses),
    ):
        h_mean = _mean(depths[p] for p in h_set if p in depths)
        m_mean = _mean(depths[p] for p in m_set if p in depths)
        gap = m_mean - h_mean

        n1 = null_unmatched(h_vocab, depths, len(set(m_set)))
        n1_lo, n1_hi = _interval(n1)
        n1_p = _pval(m_mean, n1)

        n2, matched, unmatched = null_region_matched(
            h_vocab, depths, namespaces,
            [p for p in m_set if p in depths and p in namespaces])
        n2_lo, n2_hi = _interval(n2)
        n2_p = _pval(m_mean, n2)
        n2_mean = _mean(n2)

        # Louvain cross-check, known degenerate — reported, not relied on.
        nl, _, _ = null_region_matched(
            h_vocab, depths, communities,
            [p for p in m_set if p in depths and p in communities])
        nl_mean, nl_p = _mean(nl), _pval(m_mean, nl)

        # How much of the raw gap does region matching absorb?
        explained = (
            (n2_mean - h_mean) / gap if gap else float("nan")
        )

        print()
        print("=" * 78)
        print(f"{level.upper()} LEVEL")
        print("=" * 78)
        print(f"  human mean depth   {h_mean:8.3f}")
        print(f"  machine mean depth {m_mean:8.3f}   gap {gap:+.3f}")
        print(f"  N1 unmatched null      mean {_mean(n1):7.3f}  "
              f"95% [{n1_lo:.3f}, {n1_hi:.3f}]  p={n1_p:.4f}"
              f"   {'REJECTS' if n1_p < 0.05 else 'does not reject'}")
        print(f"  N2 region-matched null mean {n2_mean:7.3f}  "
              f"95% [{n2_lo:.3f}, {n2_hi:.3f}]  p={n2_p:.4f}"
              f"   {'REJECTS' if n2_p < 0.05 else 'does not reject'}")
        print(f"  region matching absorbs {explained:.1%} of the raw gap"
              f"   (unmatchable premises: {unmatched})")
        print(f"  [Louvain cross-check, degenerate partition: null mean "
              f"{nl_mean:.3f}  p={nl_p:.4f}]")

        rows.append({
            "level": level, "human_mean": h_mean, "machine_mean": m_mean,
            "gap": gap,
            "n1_null_mean": _mean(n1), "n1_lo": n1_lo, "n1_hi": n1_hi,
            "n1_p": n1_p,
            "n2_null_mean": n2_mean, "n2_lo": n2_lo, "n2_hi": n2_hi,
            "n2_p": n2_p, "region_explained_fraction": explained,
            "matched_fraction": matched, "unmatchable": unmatched,
            "louvain_null_mean": nl_mean, "louvain_p": nl_p,
        })

    # Namespace cross-check on the type level: where does each corpus live?
    print()
    print("=" * 78)
    print("WHERE THE TWO VOCABULARIES LIVE — top namespaces by share")
    print("=" * 78)
    hn = collections.Counter(_region_namespace(p) for p in h_vocab)
    mn = collections.Counter(_region_namespace(p) for p in m_vocab)
    ns_rows = []
    print(f"{'namespace':<16}{'mach share':>11}{'hum share':>10}"
          f"{'mach depth':>11}{'hum depth':>10}{'within-ns gap':>14}")
    h_by_ns: dict[str, list[str]] = collections.defaultdict(list)
    for p in h_vocab:
        if p in depths:
            h_by_ns[_region_namespace(p)].append(p)
    for ns, cnt in mn.most_common(12):
        md = _mean(depths[p] for p in m_vocab
                   if _region_namespace(p) == ns and p in depths)
        hd = _mean(depths[p] for p in h_by_ns.get(ns, []))
        print(f"{ns:<16}{cnt / len(m_vocab):>11.4f}"
              f"{hn.get(ns, 0) / len(h_vocab):>10.4f}{md:>11.2f}{hd:>10.2f}"
              f"{md - hd:>+14.2f}")
        ns_rows.append({"namespace": ns, "machine_share": cnt / len(m_vocab),
                        "human_share": hn.get(ns, 0) / len(h_vocab),
                        "machine_mean_depth": md, "human_mean_depth": hd,
                        "within_namespace_gap": md - hd,
                        "human_premises_in_ns": len(h_by_ns.get(ns, []))})

    print()
    print("=" * 78)
    print("INSTRUMENT CHECK — is the blind spot depth-correlated? (human side)")
    print("=" * 78)
    bias = instrument_depth_bias()
    b = bias.iloc[0]
    print(f"  recovered targets {int(b['recovered_n']):>7,}  "
          f"mean depth {b['recovered_mean_depth']:.3f}")
    print(f"  MISSED targets    {int(b['missed_n']):>7,}  "
          f"mean depth {b['missed_mean_depth']:.3f}")
    print(f"  bias (recovered - missed) {b['bias']:+.3f}")
    print("  A POSITIVE bias means the extractor drops SHALLOW premises, so")
    print("  measured depth is inflated -- and inflated more where recall is")
    print("  worse, which is the machine side.")
    bias.to_csv(config.RESULTS / "depth_instrument_bias.csv", index=False)

    frame = pd.DataFrame(rows)
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    frame.to_csv(config.RESULTS / "depth_mechanism.csv", index=False)
    pd.DataFrame(ns_rows).to_csv(
        config.RESULTS / "depth_namespace_shares.csv", index=False)

    print()
    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    for r in rows:
        verdict = ("TOPOLOGICAL (reading B) — region matching absorbs the gap"
                   if r["n2_p"] >= 0.05
                   else "BEHAVIOURAL (reading A) — gap survives region matching")
        print(f"  {r['level']:<6} N2 p={r['n2_p']:.4f}  "
              f"absorbs {r['region_explained_fraction']:.1%}  -> {verdict}")
    print(f"\nwrote 2 CSVs to {config.RESULTS}")


if __name__ == "__main__":
    import sys

    a = [int(x) if x != "all" else None for x in sys.argv[1:]]
    main(*(a or [None, None]))
