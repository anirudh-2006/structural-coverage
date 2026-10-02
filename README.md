# Structural Coverage

**Do AI provers use mathlib the way mathematicians do?**

Code and committed results for *Structural Coverage: Do AI Provers Use Mathlib
the Way Mathematicians Do?* (MATH-AI @ NeurIPS 2026, non-archival workshop
track). Paper source and PDF: [`papers/mathai-2026/`](papers/mathai-2026/).

## Summary

A Lean proof is not only a binary success. It is a selection of premises from a
library, and that selection induces a subgraph of mathlib4's dependency graph.
Two proofs can both be correct and induce structurally different subgraphs, and
`pass@k` is blind to the difference. This repo defines structural coverage over
those induced subgraphs and compares 29,750 released machine Lean proofs
(Goedel-Prover on Lean Workbook) against 70,086 human mathlib declarations.

Three findings:

1. **Vocabulary coverage differs by one to two orders of magnitude.** 78,642
   human premises against 1,127 machine, a ratio of 69.8x, Jaccard 0.0129, with
   98.7% of the human vocabulary untouched by any machine proof. Every control
   narrows the gap and none closes it: 44.0x at equal n, 18.8x under a 1:1
   class- and step-matched design, 28.5x restricted to the 42 library regions
   the machine vocabulary inhabits.
2. **There is a characteristic concentration, and it is a stratum.**
   Arithmetic-tactic proofs of at most two tactic steps are 23.1% of the machine
   corpus and 0.02% of mathlib (14 of 70,086 declarations).
3. **A negative methodological result about the released graph.** The graph
   release's published per-declaration layer attribute is a centrality proxy,
   not a derivation-length measure. A depth finding built on it is withdrawn in
   the paper rather than reinterpreted.

The object of study is the *explicit subgraph* of mathlib4's dependency graph as
released by Li et al. (arXiv:2604.24797) — the source-visible portion
approximating human-intended dependencies. The graph is **not** rebuilt here;
the published release is consumed at a pinned revision.

The comparison has a known confound, stated in the paper's limitations: the
machine corpus targets competition statements (Lean Workbook), not mathlib
theorems, so the comparison runs over the shared premise vocabulary with
length-, class- and area-matched controls rather than over matched statements.

## Setup

Python 3.11+.

```
make setup                    # pip install -r requirements.txt
bash scripts/download_data.sh # ~2.5 GB fetched at pinned revisions
```

`download_data.sh` fetches all three external inputs and refuses to run if any
delegated fetch script has drifted off the pin:

| Source | Revision |
|---|---|
| `MathNetwork/MathlibGraph` (HuggingFace dataset) | `8c706461fe266802197b62af324de12a3f1aa7fb` |
| `Goedel-LM/Lean-workbook-proofs` (HuggingFace dataset) | `b731852af8d8ab11498fda27bce9020738c01c59` |
| `leanprover-community/mathlib4` (source text) | `534cf0b8f5267c3f20bf52f932ad5f9834187c35` |

Everything lands in `data/`, which is gitignored and never hand-edited. Nothing
is compiled — no Lean toolchain is installed or invoked. mathlib4 source text is
needed because the graph release ships no statements and no proof bodies, and
source-visible extraction needs the `.lean` files.

## Reproduce

```
make audit     # extraction retention on the explicit subgraph; the gate
make test      # full test suite
make lint      # ruff
```

Then the analyses, each writing committed CSVs into `results/`:

```
python -m src.extract.ceiling              # extraction ceiling
python -m src.analysis.vocabulary_contamination
python -m src.analysis.area_restricted     # the headline coverage table
python -m src.analysis.layer_composition   # infrastructure vs mathematical hubs
python -m src.analysis.common_support      # strata + rarefaction
python -m src.analysis.length_control
python -m src.analysis.tactic_strata       # instrument calibration
python -m src.analysis.proof_census
python -m src.analysis.premise_concentration  # per-premise occurrence shares
```

Sample sizes and seeds come from `src/config.py` so a clean checkout reproduces
the committed CSVs; do not pass sizes on the command line unless you intend to
produce something other than the committed artifact.

## Where the paper's numbers come from

Each row was traced to the script that writes the CSV and the exact row and
column the figure is read from. Numbers are stated in the paper rounded; the
CSVs carry full precision.

| Number | Paper | CSV | Row / column | Written by |
|---|---|---|---|---|
| **69.8x** vocabulary ratio, full corpora | §1, Table 1 | `results/coverage_area_restricted.csv` | `design="full corpora"` → `ratio` = 69.77994676131323 | `src/analysis/area_restricted.py` |
| **28.5x** ratio, area-restricted (primary control) | §1, Table 1 | `results/coverage_area_restricted.csv` | `design="restricted — support (PRIMARY)"` → `ratio` = 28.474711623779946 | `src/analysis/area_restricted.py` |
| **0.0129** Jaccard, full corpora | abstract, §1, Table 1 | `results/coverage_by_policy.csv` | `policy="corrected"` → `jaccard` = 0.012875372992190971 | `src/analysis/vocabulary_contamination.py` |
| **23.1%** arith x 0–2 steps, machine share | abstract, §1, §5 | `results/common_support_cells.csv` | `cell="arith x 0-2"` → `machine_share` = 0.230890756302521 (n = 6,869 / 29,750) | `src/analysis/common_support.py` |
| **0.6124** extraction retention | §3, §7 | `results/extraction_audit.csv` | `layer="mathematical", matcher="loose"` → `rate` (1,830 / 2,988) | `src/extract/audit.py` |
| **27.0%** `sq_nonneg` share of machine premise occurrences | abstract, §1, §5 | `results/premise_concentration.csv` | `premise="sq_nonneg"` (rank 1) → `share` = 0.2700938656154579 (16,718 / 61,897) | `src/analysis/premise_concentration.py` |
| **68.1%** top-25 premises, share of machine premise occurrences | abstract, §1, §5 | `results/premise_concentration.csv` | `rank=25` → `cumulative_share` = 0.6814869864452235 | `src/analysis/premise_concentration.py` |

Supporting numbers traced the same way:

| Number | CSV | Row / column | Written by |
|---|---|---|---|
| 78,642 human / 1,127 machine vocabulary | `results/coverage_by_policy.csv` | `policy="corrected"` → `human_vocab`, `machine_vocab` | `src/analysis/vocabulary_contamination.py` |
| 98.7% human-only fraction | `results/coverage_by_policy.csv` | `policy="corrected"` → `human_only_fraction` = 0.9871061264972916 | `src/analysis/vocabulary_contamination.py` |
| 44.0x at equal n (49,601 human premises) | `results/vocabulary_rarefaction.csv` | `corpus="human", fraction=0.4244784978455041` → `vocab_mean` = 49601.0 | `src/analysis/common_support.py` |
| 0.02% / 14 of 70,086 mathlib arith x 0–2 | `results/common_support_cells.csv` | `cell="arith x 0-2"` → `human_share` = 0.00019975458722141368 | `src/analysis/common_support.py` |
| 32,091 restricted human vocabulary, 42 regions | `results/coverage_area_restricted.csv` | `design="restricted — support (PRIMARY)"` → `human_vocab`, `n_regions` | `src/analysis/area_restricted.py` |
| 19.2x / 24.1x sensitivity arms (S1, S2) | `results/coverage_area_restricted.csv` | `design="S1 restricted — top-12 only"`, `"S2 restricted — dotted only"` → `ratio` | `src/analysis/area_restricted.py` |
| 5,222 human / 14 machine unexcluded tactic-name resolutions | `results/vocabulary_contamination.csv` | `unexcluded_tactic_name_occurrences` | `src/analysis/vocabulary_contamination.py` |
| 18.8x, 1:1 class- and step-matched design | `results/coverage_common_support.csv` | `scope="matched_1to1"` → `human_vocab` 21,162 ÷ `machine_vocab` 1,123 = 18.844167408726626 | `src/analysis/common_support.py` |
| 89.6x, mathematical hub layer only | `results/layer_composition.csv` | `mathematical` column, `corpus="human"` 75,063 ÷ `corpus="machine"` 838 = 89.57398568019093 | `src/analysis/layer_composition.py` |

### The one number this release cannot regenerate

The paper's **5.7x** exploratory genre-matched ratio was a one-off measurement,
not a pipeline output. It was taken by hand, read-only, and no script or CSV was
ever produced for it, so it cannot be regenerated from this release. Its change
record gives the figures in full:

| Corpus | Proofs | Distinct premises |
|---|---|---|
| mathlib `Archive/Imo` | 508 declarations | 1,101 |
| Goedel, rarefied to 508 proofs over 20 seeds | 508 | 193 mean (range 164–227) |
| | | **5.7x** |

The paper labels it exploratory and not pre-registered, and reports it as a
lower bound: 467 of the 508 declarations cite at least one local lemma the
extractor cannot see, `Archive` lying outside the graph's build target, which
also leaves it outside the extraction audit. It is not a control and is not
reported as one.

### Known gaps

- **The paper's figures are not regenerable from this snapshot.** The script
  that produced them is not included, and the `figures` make target that
  referenced it has been removed rather than left broken.
- **Provenance comments point outside this release.** Roughly 60 docstrings and
  comments across `src/` and `tests/` cite `CLAUDE.md` sections and
  `notes/changes/*.md` change records, neither of which is included in this
  public snapshot. The references are stale here; the source was deliberately
  left unmodified rather than rewritten.
- **DeepSeek-Prover-V1 and Goedel-Prover-V2 are not included.** One machine
  corpus only, as stated in the paper's scope.

## Layout

```
scripts/      pinned fetchers; download_data.sh is the entry point
src/
  config.py   paths, pinned revisions, frozen metric parameters, seeds
  graph/      load and query the published mathlib dependency graph
  extract/    source-visible premise extraction and the retention audit
  metrics/    the structural coverage metrics
  analysis/   the comparisons and controls
tests/        the extraction audit lives here as an assertion
results/      committed CSVs
papers/
  mathai-2026/  paper source (LaTeX), compiled PDF, methods and limitations notes
```

## Citing

The paper is a non-archival workshop submission. Please cite the published
mathlib graph it builds on:

> Li, Peng, Severini, Shafto. *The Network Structure of Mathlib.*
> arXiv:2604.24797, 2026.

## License

MIT, see [`LICENSE`](LICENSE).
