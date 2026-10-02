"""E-R2: does the coverage gap survive on the machine's own library territory?

THE OBJECTION THIS ANSWERS. R2, the paper's primary review risk: the machine
corpus is Lean Workbook competition statements and the human corpus is all of
mathlib, so the vocabulary gap may reflect PROBLEM SELECTION rather than
anything about proofs. The control restricts the human corpus to the library
regions the machine vocabulary actually occupies and re-measures coverage
there.

WHY THIS CONTROL AND NOT THE STRONGER ONE. A same-problem comparison — machine
against human proofs of identical statements — is not available. The only Lean
4 human miniF2F proofs in existence are 67, and they are DeepSeek-Prover-V1.5's
own few-shot prompt pool (`datasets/minif2f_valid_few_shot.jsonl`); the
LeanDojo Lean 4 port is 488/488 `sorry`, and the 155 proofs in the original
miniF2F are Lean 3. Scoped and dropped 2026-09-02. See
`notes/changes/2026-09-03-area-restricted-coverage-prediction.md`.

WHAT THIS CONTROL CANNOT DO. It cannot address selection WITHIN a region.
`Nat` holds both competition arithmetic and the analytic number theory no
competition problem touches; restricting to `Nat` does not equalise that.

THE RULE WAS FIXED BEFORE THE RUN. Support-based — every region containing at
least one machine premise — so there is no threshold and no top-k. Two
sensitivities (S1 top-12, S2 dotted-only) were registered at the same time and
are reported whatever they show. Nothing here is a new metric:
`structural.coverage_overlap` is called unmodified, on the same cached
corrected premise sets as the primary result.
"""

from __future__ import annotations

import pandas as pd

from src import config
from src.analysis import proof_census
from src.metrics import structural

ROOT_REGION = "_root_"

# The twelve namespaces committed in results/depth_namespace_shares.csv, which
# is the existing decomposition. Named here for sensitivity S1 only — the
# primary rule does not use a cutoff.
TOP12 = (
    "Nat", "Real", "Int", "Finset", "Complex", "Set",
    "Matrix", "Polynomial", "Fin", "Function", "Rat", "List",
)


def region(name: str) -> str:
    """Top-level region of a premise.

    `depth_mechanism._region_namespace` with ONE amendment, registered before
    the run: an undotted name maps to a single shared `_root_` region rather
    than to itself. As committed it returns the bare name, which under a
    support-based restriction is degenerate — each root-level machine premise
    would admit exactly itself from the human side, which is not a region
    restriction at all. Collapsing them is the only reading under which
    root-level (`add_comm`, `sq_nonneg`, `mul_le_mul`) counts as machine
    territory, and it is the INCLUSIVE choice: it makes the restricted human
    corpus larger and the measured ratio larger.
    """
    return name.split(".", 1)[0] if "." in name else ROOT_REGION


def regions_of(vocab: set[str]) -> set[str]:
    return {region(p) for p in vocab}


def restrict(vocab: set[str], allowed: set[str]) -> set[str]:
    return {p for p in vocab if region(p) in allowed}


def _row(design: str, human: set[str], machine: set[str],
         human_full: set[str], machine_full: set[str]) -> dict:
    """One coverage row. `coverage_overlap` is called unmodified."""
    cov = structural.coverage_overlap(machine, human)
    return {
        "design": design,
        "human_vocab": len(human),
        "machine_vocab": len(machine),
        "ratio": len(human) / len(machine) if machine else float("nan"),
        "jaccard": cov["jaccard"],
        "intersection": cov["intersection"],
        "human_only": cov["human_only"],
        "human_only_fraction": cov["human_only_fraction"],
        "human_survival": len(human) / len(human_full) if human_full else float("nan"),
        "machine_leak": (
            1 - len(machine) / len(machine_full) if machine_full else float("nan")),
        "n_regions": len(regions_of(human)) if human else 0,
    }


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    human_full = set(proof_census.vocabulary(proof_census.census("human")))
    machine_full = set(proof_census.vocabulary(proof_census.census("machine")))

    r_support = regions_of(machine_full)
    r_top12 = {n for n in TOP12 if n in r_support}
    r_dotted = r_support - {ROOT_REGION}

    designs = [
        ("full corpora", human_full, machine_full),
        ("restricted — support (PRIMARY)",
         restrict(human_full, r_support), restrict(machine_full, r_support)),
        ("S1 restricted — top-12 only",
         restrict(human_full, r_top12), restrict(machine_full, r_top12)),
        ("S2 restricted — dotted only",
         restrict(human_full, r_dotted), restrict(machine_full, r_dotted)),
    ]
    coverage = pd.DataFrame(
        [_row(d, h, m, human_full, machine_full) for d, h, m in designs])

    # Where the restriction's mass actually sits, so "the restriction is doing
    # something other than intended" is checkable rather than asserted.
    rows = []
    for reg in sorted(r_support,
                      key=lambda x: -sum(1 for p in machine_full if region(p) == x)):
        m = sum(1 for p in machine_full if region(p) == reg)
        h = sum(1 for p in human_full if region(p) == reg)
        rows.append({"region": reg, "machine_premises": m, "human_premises": h,
                     "machine_share": m / len(machine_full),
                     "human_share_of_full": h / len(human_full)})
    breakdown = pd.DataFrame(rows)
    return coverage, breakdown


def main() -> None:
    coverage, breakdown = run()
    coverage.to_csv(config.RESULTS / "coverage_area_restricted.csv", index=False)
    breakdown.to_csv(
        config.RESULTS / "coverage_area_restricted_regions.csv", index=False)

    pd.set_option("display.width", 200)
    print("\nCOVERAGE UNDER AREA RESTRICTION")
    print(coverage.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(f"\nregions in support rule: {len(breakdown)}")
    print("\nTOP REGIONS BY MACHINE MASS")
    print(breakdown.head(15).to_string(
        index=False, float_format=lambda v: f"{v:.4f}"))


if __name__ == "__main__":
    main()
