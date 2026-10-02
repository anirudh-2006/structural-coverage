"""Per-premise occurrence concentration in the machine corpus.

REPRODUCTION ONLY. Two figures were quoted in the frozen MATH-AI submission
without a committed table behind them:

    sq_nonneg      27.0% of all machine premise occurrences
    top-25         68.1% of all machine premise occurrences

Their provenance record says so explicitly -- "NOT IN ANY CSV. Per-premise
occurrence shares were computed for the frozen MATH-AI submission and the
per-premise table was not committed to results/" (paper-vericode/numbers.tex)
-- and `notes/decisions.md` carries them in prose. This module computes the
missing table so both are readable off a committed artifact.

It adds no metric and changes no definition. The occurrence basis is the one
already frozen in `vocabulary_contamination.contamination_table`, which reports
`occurrences_corrected` as

    sum(len(s) for s in pc.premise_sets(frame))

so an occurrence is a (proof, premise) pair under the corrected exclusion
policy: per-proof premise SETS, self-name dropped, keyword declarations
dropped. A premise cited twice inside one proof counts once. The denominator is
therefore the committed 61,897, asserted below -- not a recount.

Both hub layers are included. The mathematical-layer-only view is a different
basis (results/layer_composition.csv, machine mathematical = 838) and is not
what these two figures were computed on.

DESCRIPTIVE AND POST-HOC, as labelled wherever they are used. The source line
in notes/decisions.md records them alongside the withdrawn depth analysis; they
do not support any depth claim.
"""

from __future__ import annotations

import pandas as pd

from .. import config
from . import proof_census as pc

# results/vocabulary_contamination.csv, corpus=machine, occurrences_corrected.
# The committed value this table must sum to.
MACHINE_OCCURRENCES_CORRECTED = 61_897

# How many ranks the paper's second figure aggregates over.
TOP_K = 25


def occurrence_table(machine: pd.DataFrame) -> pd.DataFrame:
    """Per-premise occurrence counts, descending, with cumulative share."""
    counts: dict[str, int] = {}
    for premises in pc.premise_sets(machine):
        for p in premises:
            counts[p] = counts.get(p, 0) + 1

    total = sum(counts.values())
    if total != MACHINE_OCCURRENCES_CORRECTED:
        raise AssertionError(
            f"occurrence total {total:,} != committed "
            f"{MACHINE_OCCURRENCES_CORRECTED:,} "
            "(results/vocabulary_contamination.csv, corpus=machine, "
            "occurrences_corrected). The exclusion policy or the census "
            "cache has moved; reconcile before reporting a share."
        )

    frame = pd.DataFrame(
        sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])),
        columns=["premise", "occurrences"],
    )
    frame.insert(0, "rank", range(1, len(frame) + 1))
    frame["share"] = frame["occurrences"] / total
    frame["cumulative_share"] = frame["share"].cumsum()
    return frame


def main() -> None:
    machine = pc.census("machine")
    frame = occurrence_table(machine)

    config.RESULTS.mkdir(parents=True, exist_ok=True)
    out = config.RESULTS / "premise_concentration.csv"
    frame.to_csv(out, index=False)

    total = int(frame["occurrences"].sum())
    sq = frame[frame["premise"] == "sq_nonneg"]
    top_k = float(frame["cumulative_share"].iloc[TOP_K - 1])

    print(f"machine proofs            {len(machine):>8,}")
    print(f"premise vocabulary        {len(frame):>8,}")
    print(f"premise occurrences       {total:>8,}  (corrected, both layers)")
    print()
    if len(sq):
        row = sq.iloc[0]
        print(f"sq_nonneg                 {int(row['occurrences']):>8,}  "
              f"{row['share'] * 100:.1f}%  (rank {int(row['rank'])})")
    else:
        print("sq_nonneg                    ABSENT")
    print(f"top-{TOP_K} cumulative        {'':>8}  {top_k * 100:.1f}%")
    print()
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
