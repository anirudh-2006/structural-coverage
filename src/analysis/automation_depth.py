"""Is the +23.6 depth gap automation-emitted premises, or deeper mathematics?

WITHDRAWN 2026-09-04 — THIS MODULE SUPPORTS NO CLAIM IN THE PAPER. It tests
a mechanism for a gap in `dag_layer`, which the 2026-08-23 audit showed is a
centrality proxy, not distance from primitives. The depth finding is withdrawn
(notes/changes/2026-09-04-depth-withdrawn.md); everything below is retained as
the record of how it was investigated, not as a live result. Do not quote its
figures.

Pre-registered in `notes/changes/2026-08-23-automation-depth-prediction.md`.
Result in `notes/changes/2026-08-23-automation-depth.md`.

THE QUESTION. `depth_reach` says machine premises are +23.6 deeper (matched
design) and the namespace-matched null absorbed only 3.2%, so it is not a
composition effect over library regions. One mechanism was never tested: the
machine corpus is 96.0% automation against the human corpus's 49.6%, and
tactic implementations emit term constants (`Mathlib.Meta.NormNum.isNat_*`,
`Nat.rawCast`) that sit deep in the DAG whatever the proof was doing. The
namespace null cannot absorb those -- it matches on where a premise lives, and
these genuinely live deep.

  Reading A  machine proofs draw on deeper MATHEMATICS -- behavioural, H2b
             stands as a humans-vs-machines finding.
  Reading B  AUTOMATION reaches deep infrastructure -- a statement about what
             `nlinarith` emits, which cannot carry H2b.

WHY THIS IS NOT ALREADY DONE BY `split_hub_layers`. That partition is
Lean-core-vs-Mathlib provenance. A Mathlib tactic-internal constant has a
`file_module` under `Mathlib.`, is not an instance or coercion, and is not a
kernel kind -- so it lands on the MATHEMATICAL side and is inside every depth
number this project has reported. AUTO is exactly what that partition misses.

THE EXCLUSION IS ONE CLASS, NOT THREE. The 08-16 audit named three residual
classes; only one is an automation artifact. Notation-backed definitions
(`Real`, `nhds`) are mathematical objects, and simp-set lemmas (`mul_one`) are
mathematical AND shallow -- excluding a shallow class from a test designed to
remove a deep one would confound it in the direction that flatters H2b. Both
are measured and reported as diagnostics; neither is excluded.
"""

from __future__ import annotations

import pandas as pd

from src import config
from src.analysis import common_support as cs
from src.analysis import tactic_strata as ts
from src.metrics import structural

# --- the AUTO class, frozen in the pre-registration -----------------------

AUTO_NAME_PREFIXES = (
    "Mathlib.Meta.", "Mathlib.Tactic.", "Qq.", "Lean.", "Std.Tactic.",
    "Aesop.",
)
AUTO_MODULE_PREFIXES = ("Mathlib.Tactic.", "Mathlib.Meta.")
AUTO_COMPONENTS = frozenset({"rawCast", "IsNat", "IsInt", "IsRat"})
AUTO_COMPONENT_PREFIXES = ("isNat_", "isInt_", "isRat_")

# Named EXAMPLES from the 08-16 audit record, not class rules. Reported as
# diagnostics so the decision to leave them in is auditable.
NOTATION_BACKED = frozenset({
    "Real", "Top.top", "setOf", "nhds", "Norm.norm",
    "CategoryTheory.CategoryStruct.comp", "Set.iUnion",
})
SIMP_SET_NAMED = frozenset({
    "Nat.cast_one", "mul_one", "Filter.univ_mem'", "le_refl",
})


def is_auto(name: str, attrs: dict) -> bool:
    """A1 name prefix, A2 norm_num term-constant family, A3 provenance."""
    if name.startswith(AUTO_NAME_PREFIXES):                      # A1
        return True
    parts = name.split(".")
    for comp in parts[-2:]:                                       # A2
        if comp in AUTO_COMPONENTS or comp.startswith(AUTO_COMPONENT_PREFIXES):
            return True
    module = attrs.get("file_module") or ""                       # A3
    return module.startswith(AUTO_MODULE_PREFIXES)


def auto_index(g) -> set[str]:
    return {n for n, a in g.nodes(data=True) if is_auto(n, a)}


# --- depth at type and usage level ---------------------------------------

def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def depth_levels(frame: pd.DataFrame, depths: dict[str, int],
                 drop: set[str] | None = None) -> dict:
    """Type-, usage- and per-proof-level mean depth over a corpus slice.

    type      mean over the DISTINCT premises used (the vocabulary)
    usage     mean over premise OCCURRENCES (a premise counted once per proof)
    per_proof mean over proofs of each proof's own mean premise depth --
              the quantity `common_support.summarise` reports as `depth_mean`

    All three are reported because the 08-17 record's +22.6 is type-level, its
    +23.7 is usage-level, and the matched +23.18/+23.64 in
    results/metrics_common_support.csv is per-proof. They are different
    estimands and this module must not quietly substitute one for another.
    """
    drop = drop or set()
    vocab: set[str] = set()
    usage: list[int] = []
    per_proof: list[float] = []
    occurrences = 0
    kept_proofs = 0
    for premises in frame["premise_set"]:
        kept = {p for p in premises if p not in drop}
        occurrences += len(kept)
        placed = [depths[p] for p in kept if p in depths]
        if placed:
            per_proof.append(_mean(placed))
            kept_proofs += 1
        usage.extend(placed)
        vocab |= kept
    vocab_placed = [depths[p] for p in vocab if p in depths]
    return {
        "vocab": len(vocab),
        "vocab_placed": len(vocab_placed),
        "occurrences": occurrences,
        "proofs_with_premises": kept_proofs,
        "depth_type": _mean(vocab_placed),
        "depth_usage": _mean(usage),
        "depth_per_proof": _mean(per_proof),
    }


def class_mass(frame: pd.DataFrame, depths: dict[str, int],
               members: set[str], label: str, corpus: str) -> dict:
    """Mass and mean depth of one premise class within a corpus slice."""
    vocab: set[str] = set()
    hits = 0
    total = 0
    placed: list[int] = []
    for premises in frame["premise_set"]:
        total += len(premises)
        for p in premises:
            if p in members:
                hits += 1
                vocab.add(p)
                if p in depths:
                    placed.append(depths[p])
    return {
        "corpus": corpus, "class": label,
        "vocab": len(vocab),
        "occurrences": hits,
        "occurrence_share": hits / total if total else float("nan"),
        "mean_depth": _mean(placed),
    }


# --- support check after exclusion ---------------------------------------

def support_after_exclusion(human: pd.DataFrame, machine: pd.DataFrame,
                            drop: set[str],
                            min_human: int = config.LENGTH_CELL_MIN_N
                            ) -> pd.DataFrame:
    """Cells whose mass collapses once AUTO premises are removed.

    Removing premises can empty a proof's premise set, which drops it out of
    every depth mean. The pre-registered cell-collapse criterion is checked
    against proofs that still HAVE premises, per cell.
    """
    def counts(frame):
        kept = frame["premise_set"].map(
            lambda s: len({p for p in s if p not in drop}) > 0)
        return frame[kept]["cell"].value_counts()

    h_before = human["premise_set"].map(bool)
    m_before = machine["premise_set"].map(bool)
    hb = human[h_before]["cell"].value_counts()
    mb = machine[m_before]["cell"].value_counts()
    ha, ma = counts(human), counts(machine)

    rows = []
    for cell in sorted(set(hb.index) | set(mb.index)):
        rows.append({
            "cell": cell,
            "human_before": int(hb.get(cell, 0)),
            "human_after": int(ha.get(cell, 0)),
            "machine_before": int(mb.get(cell, 0)),
            "machine_after": int(ma.get(cell, 0)),
            "supported_after": (int(ha.get(cell, 0)) >= min_human
                                and int(ma.get(cell, 0)) > 0),
        })
    return pd.DataFrame(rows)


# --- entry point ----------------------------------------------------------

def main() -> None:
    human, machine = cs.prepare("human"), cs.prepare("machine")
    g = ts._explicit_graph()
    depths = structural.depth_index(g)

    cells = cs.cell_table(human, machine)
    supported = set(cells[cells["supported"]]["cell"])
    h_sup, m_sup = cs.restrict(human, supported), cs.restrict(machine, supported)
    h_match, m_match = cs.match(human, machine, supported)

    auto = auto_index(g)
    print("=" * 78)
    print("AUTO CLASS — automation-emitted / tactic-implementation constants")
    print("=" * 78)
    print(f"AUTO members in the explicit graph: {len(auto):,} of {g.number_of_nodes():,}")

    def fmt(x):
        return f"{x:.4f}"

    # --- Q1/Q3: mass of AUTO and of the two reported-not-excluded classes ---
    mass_rows = []
    for corpus, frame in (("human", h_sup), ("machine", m_sup)):
        mass_rows.append(class_mass(frame, depths, auto, "AUTO", corpus))
        mass_rows.append(class_mass(frame, depths, set(NOTATION_BACKED),
                                    "notation_backed(named)", corpus))
        mass_rows.append(class_mass(frame, depths, set(SIMP_SET_NAMED),
                                    "simp_set(named)", corpus))
    mass = pd.DataFrame(mass_rows)
    print("\nCLASS MASS in the common-support region:")
    print(mass.to_string(index=False, float_format=fmt))

    m_auto_share = float(
        mass[(mass.corpus == "machine") & (mass["class"] == "AUTO")]
        ["occurrence_share"].iloc[0])
    collapsed = m_auto_share < 0.02
    print(f"\nmachine AUTO occurrence share = {m_auto_share:.4f}  "
          f"-> {'UNINFORMATIVE BY COLLAPSE (<0.02)' if collapsed else 'above the 0.02 floor'}")

    # --- Q2: the gap with and without AUTO, at three levels ---------------
    rows = []
    for scope, hf, mf in (("full", human, machine),
                          ("support", h_sup, m_sup),
                          ("matched", h_match, m_match)):
        for policy, drop in (("with_auto", set()), ("without_auto", auto)):
            for corpus, frame in (("human", hf), ("machine", mf)):
                rows.append({"scope": scope, "policy": policy,
                             "corpus": corpus,
                             **depth_levels(frame, depths, drop)})
    levels = pd.DataFrame(rows)
    print()
    print("=" * 78)
    print("DEPTH WITH AND WITHOUT THE AUTO CLASS")
    print("=" * 78)
    print(levels.to_string(index=False, float_format=fmt))

    gap_rows = []
    for scope in ("full", "support", "matched"):
        for policy in ("with_auto", "without_auto"):
            sel = levels[(levels.scope == scope) & (levels.policy == policy)]
            h = sel[sel.corpus == "human"].iloc[0]
            m = sel[sel.corpus == "machine"].iloc[0]
            gap_rows.append({
                "scope": scope, "policy": policy,
                "gap_type": m["depth_type"] - h["depth_type"],
                "gap_usage": m["depth_usage"] - h["depth_usage"],
                "gap_per_proof": m["depth_per_proof"] - h["depth_per_proof"],
            })
    gaps = pd.DataFrame(gap_rows)
    print("\nGAPS (machine - human):")
    print(gaps.to_string(index=False, float_format=fmt))

    print("\nABSORBED BY EXCLUDING AUTO (fraction of the with_auto gap):")
    for scope in ("full", "support", "matched"):
        w = gaps[(gaps.scope == scope) & (gaps.policy == "with_auto")].iloc[0]
        o = gaps[(gaps.scope == scope) & (gaps.policy == "without_auto")].iloc[0]
        parts = []
        for k in ("gap_type", "gap_usage", "gap_per_proof"):
            parts.append(f"{k.replace('gap_', '')} "
                         f"{(w[k] - o[k]) / w[k]:+.4f}" if w[k] else f"{k} n/a")
        print(f"  {scope:<9}" + "  ".join(parts))

    # --- cell-collapse check ---------------------------------------------
    support = support_after_exclusion(h_sup, m_sup, auto)
    lost = support[~support["supported_after"]]
    print()
    print("=" * 78)
    print("CELL COLLAPSE CHECK (pre-registered)")
    print("=" * 78)
    if len(lost):
        print(lost.to_string(index=False))
        lost_mass = (m_sup[m_sup["cell"].isin(set(lost["cell"]))].shape[0]
                     / len(m_sup))
        print(f"machine mass falling out of support: {lost_mass:.4f}"
              f"  -> {'INCONCLUSIVE (>0.20)' if lost_mass > 0.20 else 'within tolerance'}")
    else:
        print("no cell loses support once AUTO premises are removed")

    config.RESULTS.mkdir(parents=True, exist_ok=True)
    mass.to_csv(config.RESULTS / "automation_depth_class_mass.csv", index=False)
    levels.to_csv(config.RESULTS / "automation_depth_levels.csv", index=False)
    gaps.to_csv(config.RESULTS / "automation_depth_gaps.csv", index=False)
    support.to_csv(config.RESULTS / "automation_depth_support.csv", index=False)
    print(f"\nwrote 4 CSVs to {config.RESULTS}")


if __name__ == "__main__":
    main()
