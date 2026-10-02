"""Two identifier classes resolve on the human side and cannot resolve on the
machine side. Both inflate the paper's PRIMARY result.

The primary result (`notes/changes/2026-08-17-coverage-primary.md`) is a
human-vs-machine premise-VOCABULARY comparison: 118,514 distinct premises
against 1,127, Jaccard 0.0089, 99.1% human-only. It was promoted to primary
because it is a direct count needing no standardization, no length control
and no imputation. A direct count is only as good as what goes into the set,
and two things go into the human set that cannot go into the machine set:

  1. **The declaration's own name.** Extraction runs at declaration scope
     (correctly — `is_explicit` edges come from the elaborated term of the
     whole declaration), so `theorem Foo.bar : ...` puts `Foo.bar` into its
     own premise set. Nothing is its own explicit dependency, so this is a
     false positive by construction, and `tactic_strata` already counts it as
     spurious. It fires on 98.4% of human declarations. It fires on 0% of
     Goedel proofs, whose `lean_workbook_*` names are not mathlib
     declarations and therefore never resolve.

  2. **The `lemma` keyword.** `lemma` is a real mathlib declaration —
     `Mathlib.Tactic.Lemma`, kind `definition` — so every mathlib file that
     writes `lemma` resolves it as a premise. It is absent from
     `audit._KEYWORDS`, which does exclude `have`, `show`, `exact` and the
     tactic names, so this is an omission from that list rather than a new
     exclusion criterion. Every Goedel proof is written `theorem`, which is
     core syntax and not a declaration, so again the machine side cannot
     acquire it.

Neither is a judgement call about what counts as a premise. Both are names
the extractor resolves because a keyword or a definition site happens to
collide with a declaration name, and both are structurally unavailable to the
other corpus.

WHAT IS *NOT* EXCLUDED, AND WHY. `symm` (4.6% of human declarations) and
`trans` (2.8%) are tactic names that are also mathlib theorems, and
`audit._KEYWORDS` excludes some tactic names (`congr`, `ext`, `subst`) but not
these. That inconsistency is real. It is reported here and left in place:
extending a keyword list one name at a time after seeing which names inflate a
favourable result is the researcher-degrees-of-freedom hazard CLAUDE.md §6
exists to prevent, and the magnitude is small — two vocabulary entries and
1.2% of corrected human premise occurrences. It is the author's call, and it
is stated so a reviewer meets it here rather than deriving it.

DIRECTION. Both corrections shrink the human vocabulary and leave the machine
vocabulary untouched, so both move the primary result AGAINST the paper's
hypothesis. That is why they are applied rather than argued about.
"""

from __future__ import annotations

import pandas as pd

from src import config
from src.analysis import proof_census as pc
from src.analysis import tactic_strata as ts
from src.graph import load
from src.metrics import structural

# The exclusion policies, reported side by side. `raw` reproduces the
# 2026-08-17 numbers exactly and is kept so the correction is auditable.
POLICIES = (
    ("raw", False, False),
    ("drop_self_name", True, False),
    ("drop_keyword_lemma", False, True),
    ("corrected", True, True),
)

# Tactic names that are also mathlib declarations and are NOT excluded. See
# the module docstring: measured, reported, left alone.
UNEXCLUDED_TACTIC_NAMES = ("symm", "trans")


def _classed(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["cls"] = frame["tactics"].map(lambda t: ts.assign_class(set(t)))
    return frame


# --- 1. how much contamination, and on which side -------------------------

def contamination_table(human: pd.DataFrame, machine: pd.DataFrame
                        ) -> pd.DataFrame:
    rows = []
    for label, frame in (("human", human), ("machine", machine)):
        raw = pc.vocabulary(frame, drop_self=False, drop_keywords=False)
        occ_raw = int(frame["premises"].map(len).sum())
        unexcluded = sum(
            1 for ps in frame["premises"]
            for p in ps if p in UNEXCLUDED_TACTIC_NAMES
        )
        rows.append({
            "corpus": label,
            "proofs": len(frame),
            "vocabulary_raw": len(raw),
            "occurrences_raw": occ_raw,
            "self_hit_rate": float(frame["self_hit"].mean()),
            "keyword_hit_rate": float((frame["keyword_hits"] > 0).mean()),
            "vocabulary_corrected": len(pc.vocabulary(frame)),
            "occurrences_corrected": int(
                sum(len(s) for s in pc.premise_sets(frame))),
            "unexcluded_tactic_name_occurrences": unexcluded,
        })
    return pd.DataFrame(rows)


# --- 2. the primary result under each policy ------------------------------

def coverage_by_policy(human: pd.DataFrame, machine: pd.DataFrame
                       ) -> pd.DataFrame:
    rows = []
    for label, drop_self, drop_kw in POLICIES:
        hv = pc.vocabulary(human, drop_self=drop_self, drop_keywords=drop_kw)
        mv = pc.vocabulary(machine, drop_self=drop_self, drop_keywords=drop_kw)
        hp = pc.premise_sets(human, drop_self=drop_self, drop_keywords=drop_kw)
        mp = pc.premise_sets(machine, drop_self=drop_self, drop_keywords=drop_kw)
        cov = structural.coverage_overlap(set(mv), set(hv))
        rows.append({
            "policy": label,
            "human_vocab": len(hv), "machine_vocab": len(mv),
            "jaccard": cov["jaccard"], "intersection": cov["intersection"],
            "human_only": cov["human_only"], "machine_only": cov["machine_only"],
            "human_only_fraction": cov["human_only_fraction"],
            "human_premises_per_proof": sum(len(s) for s in hp) / len(hp),
            "machine_premises_per_proof": sum(len(s) for s in mp) / len(mp),
        })
    return pd.DataFrame(rows)


# --- 3. the precision artifact under each policy --------------------------

def spurious_by_policy(human: pd.DataFrame, machine: pd.DataFrame
                       ) -> pd.DataFrame:
    """Human per-class spurious rates, censused, and the class-route gap.

    A CENSUS, not the 4,000-proof sample of `analysis.spurious_symmetry`, so
    the absolute levels are not comparable with the frozen constants; the
    quantity of interest is the raw-vs-corrected MOVE on one fixed basis.

    Spurious is measured exactly as `tactic_strata` measures it: a resolved
    name that is not a successor of the declaration in the FULL dependency
    graph. Machine proofs have no node in that graph, so the machine rate is
    imputed by standardizing the human per-class rates onto the machine class
    mix — the class route, per `H2_SPURIOUS_ROUTE`.
    """
    g_explicit = ts._explicit_graph()
    g_full = load.load_declaration_graph()
    known = frozenset(load.declaration_names(g_explicit))

    human_mix = human["cls"].value_counts(normalize=True).to_dict()
    machine_mix = machine["cls"].value_counts(normalize=True).to_dict()

    rows = []
    for label, drop_self, drop_kw in POLICIES:
        sets = pc.premise_sets(human, drop_self=drop_self, drop_keywords=drop_kw)
        resolved = {c: 0 for c in ts.ALL_CLASSES}
        spurious = {c: 0 for c in ts.ALL_CLASSES}
        for name, cls, premises in zip(human["name"], human["cls"], sets):
            targets = ({t for t in g_full.successors(name) if t in known}
                       if name in g_full else set())
            resolved[cls] += len(premises)
            spurious[cls] += len(premises - targets)
        rate = {c: (spurious[c] / resolved[c] if resolved[c] else float("nan"))
                for c in ts.ALL_CLASSES}
        imputed_human = sum(human_mix.get(c, 0.0) * rate[c]
                            for c in ts.ALL_CLASSES if rate[c] == rate[c])
        imputed_machine = sum(machine_mix.get(c, 0.0) * rate[c]
                              for c in ts.ALL_CLASSES if rate[c] == rate[c])
        for c in ts.ALL_CLASSES:
            rows.append({
                "policy": label, "class": c, "resolved": resolved[c],
                "spurious": spurious[c], "spurious_rate": rate[c],
                "human_mix": human_mix.get(c, 0.0),
                "machine_mix": machine_mix.get(c, 0.0),
                "imputed_human": imputed_human,
                "imputed_machine": imputed_machine,
                "class_route_gap": imputed_machine - imputed_human,
            })
    return pd.DataFrame(rows)


def main() -> None:
    human = _classed(pc.census("human"))
    machine = _classed(pc.census("machine"))

    contamination = contamination_table(human, machine)
    coverage = coverage_by_policy(human, machine)
    spurious = spurious_by_policy(human, machine)

    def fmt(x):
        return f"{x:.4f}"

    print("=" * 78)
    print("CONTAMINATION — which corpus can acquire these names at all")
    print("=" * 78)
    print(contamination.to_string(index=False, float_format=fmt))

    print()
    print("=" * 78)
    print("THE PRIMARY RESULT UNDER EACH EXCLUSION POLICY")
    print("=" * 78)
    print(coverage.to_string(index=False, float_format=fmt))

    print()
    print("=" * 78)
    print("PRECISION ARTIFACT (class route, censused) UNDER EACH POLICY")
    print("=" * 78)
    print(spurious.to_string(index=False, float_format=fmt))
    gaps = spurious.groupby("policy", sort=False)["class_route_gap"].first()
    print()
    for policy, gap in gaps.items():
        direction = ("machine looks LESS spurious -> COMPOUNDS the recall "
                     "artifact" if gap < 0 else
                     "machine looks MORE spurious -> OFFSETS it")
        print(f"  {policy:<20} gap {gap:+.4f}   {direction}")

    config.RESULTS.mkdir(parents=True, exist_ok=True)
    contamination.to_csv(
        config.RESULTS / "vocabulary_contamination.csv", index=False)
    coverage.to_csv(config.RESULTS / "coverage_by_policy.csv", index=False)
    spurious.to_csv(config.RESULTS / "spurious_by_policy.csv", index=False)
    print(f"\nwrote 3 CSVs to {config.RESULTS}")


if __name__ == "__main__":
    main()
