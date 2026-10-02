"""Layer composition of the two premise vocabularies.

WHAT THIS IS. A count, not a metric. It takes the two corrected premise
vocabularies already used for the coverage result and asks, of each, how many
members sit in the language-infrastructure layer and how many in the
mathematical layer. Nothing is aggregated, weighted or standardized: every
number here is `len(vocabulary & layer)`.

WHY IT EXISTS. `paper/methods.md` M2.3 and M6 report this split (human 3,579 /
75,063, machine 289 / 838) and no committed CSV carried it, so the figures were
reproducible only by rerunning an analysis session. This module commits them.

NOTHING NEW IS DEFINED HERE. The partition is `load.split_hub_layers`, frozen
2026-08-13 and unchanged since; the vocabularies are
`proof_census.vocabulary` under the default exclusion policy, which is the
same call the coverage results make. Both are used unmodified.

WHY THIS IS NOT A CENTRALITY NUMBER. Li et al.'s Finding 3 requires the two
hub layers to be separated before any aggregate centrality score is reported.
Set membership has no aggregation step, so that rule does not bind here — and
this module makes no inference from "more infrastructure" to "less
mathematically deep", which is the inference their paper contradicts. See
M6.

UNPLACED PREMISES. A vocabulary entry resolves against the graph's declaration
names by construction, so `unplaced` should be 0 on both sides. It is emitted
as a column rather than asserted, because a non-zero value would mean the
vocabulary and the partition were cut on different graphs and every count in
the row would be wrong.
"""

from __future__ import annotations

import pandas as pd

from src import config
from src.analysis import proof_census
from src.analysis import tactic_strata as ts
from src.graph import load

CORPORA = ("human", "machine")


def compose(
    vocabulary: frozenset[str],
    infrastructure: set[str],
    mathematical: set[str],
) -> dict[str, int | float]:
    """Membership counts of one vocabulary against the frozen partition."""
    infra = vocabulary & infrastructure
    math = vocabulary & mathematical
    return {
        "vocabulary": len(vocabulary),
        "infrastructure": len(infra),
        "mathematical": len(math),
        "infrastructure_fraction": len(infra) / len(vocabulary),
        "mathematical_fraction": len(math) / len(vocabulary),
        "unplaced": len(vocabulary) - len(infra) - len(math),
    }


def run() -> pd.DataFrame:
    g = ts._explicit_graph()
    infrastructure, mathematical = load.split_hub_layers(g)

    rows = []
    for corpus in CORPORA:
        frame = proof_census.census(corpus)
        vocab = proof_census.vocabulary(frame)
        rows.append({"corpus": corpus, "proofs": len(frame),
                     **compose(vocab, infrastructure, mathematical)})
    return pd.DataFrame(rows)


def main() -> None:
    table = run()
    table.to_csv(config.RESULTS / "layer_composition.csv", index=False)

    print("\nLAYER COMPOSITION OF THE PREMISE VOCABULARIES")
    print(table.to_string(index=False, float_format=lambda v: f"{v:.4f}"))


if __name__ == "__main__":
    main()
