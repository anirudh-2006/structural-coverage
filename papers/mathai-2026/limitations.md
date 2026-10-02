# Limitations

Working text for the paper's Limitations section. Every item here is a
*stated* assumption or bound, written to be read by a reviewer who cannot ask
us a question — MATH-AI has no rebuttal phase, so each entry has to
pre-answer the objection rather than acknowledge it.

Ordered by how much damage the objection does if we do not raise it first.

---

## L1. The instrument correction transfers a human rate to a population 100× larger

**This is an assumption the paper makes, not a caveat on a result.** It is
stated here in the terms a reviewer would use to attack it.

Machine-side premise-miss rates are **not measured**. They are imputed: we
measure per-tactic-class miss rates on human mathlib proofs and standardize
them onto the machine corpus's tactic mix. The correction is only as good as
the assumption that, *within a tactic class*, the instrument misses machine
premises at the same rate it misses human ones.

The asymmetry that makes this load-bearing:

| tactic class | share of Goedel corpus | share of mathlib | mathlib declarations |
|---|---|---|---|
| `arith` (nlinarith/linarith/polyrith) | **76.4%** | **0.7%** | 475 |
| `simp` (simp/simp_all/norm_num) | 17.0% | 44.2% | 31,248 |
| `decide` (omega/decide) | 1.0% | 0.2% | 244 |
| `other` | 1.6% | 1.5% | 2,575 |
| none | 4.0% | 53.4% | 37,436 |

So more than three quarters of the machine corpus is standardized against a
human stratum comprising **0.7% of mathlib**. The rate itself is precise — 404
of those 475 declarations are sampled, effectively a census, and it is not a
small-sample problem. The exposure is that a human `nlinarith` proof and a
machine `nlinarith` proof may not be the same object. Human `nlinarith` use in
mathlib is typically a single step closing a residual goal inside a structured
proof; machine `nlinarith` use is frequently the entire proof. If the
instrument's blind spot scales with how much of the proof the automation
closes rather than merely with its presence, the transfer under-corrects.

**Direction of the residual error.** Under-correction leaves machine proofs
looking structurally narrower than they are — i.e. it biases *toward* H2.
We therefore treat the imputed correction as a lower bound on the instrument
artifact, and the H2 decision rule requires the observed gap to clear a
multiple of it rather than merely exceed it.

**What would settle it.** Elaborating machine proofs and extracting their
explicit premise sets directly, which requires reproducing the publishers'
extraction pipeline on a second corpus. The mathlib build cache for our pinned
commit is confirmed available, so this is tractable; it is not done in this
paper. Until it is, the assumption stands as stated and untested, and we say
so rather than implying the correction is measured on both sides.

---

## L2. Two automation instruments, and they are not interchangeable

Human tactic use is available from the graph publishers' jixia-extracted
lists; machine tactic use is not, so it is recovered by string matching over
proof source. We calibrated the two on the same human declarations and they
disagree materially: jixia records only main-path tactics and misses tactics
after `<;>`, inside `induction … with` case branches, and in nested
`(by simp …)` term positions. Human any-automation rate is 0.375 by jixia and
0.466 by the string matcher, an instrument component of +0.091.

Consequently all strata and mixes in this paper are cut with the string
matcher on both corpora, and jixia figures appear only as a sensitivity row.
Reported per-tactic agreement (Jaccard) ranges from 0.909 (`field_simp`) to
0.100 (`bound`).

Known false positive, retained deliberately: `bound` matches the English word
"bound" in machine proofs' natural-language comment blocks (4.1% of proofs,
0.0% after comment stripping). It sits in the `other` class and moves the
class mix by 0.0004. We did not remove it after observing this, because the
tactic list was frozen before the machine corpus was touched; we state it
instead.

---

## L3. Source-visible extraction cannot recover the explicit set in full

`is_explicit` in the published graph means "occurs in an explicit argument
position of the *elaborated* term", not "written by a human". Constants such
as `propext`, `Eq.mpr` and `of_eq_true` carry explicit in-edges in the tens of
thousands and are typed by nobody. A whole-file matching bound — which no
per-declaration extractor can beat — recovers 0.819 of mathematical-layer
explicit edges. The residual is a property of Lean's elaborator, not a defect
of our parser, which is why the extraction gate is stated as efficiency
against this measured ceiling rather than as an absolute retention figure.

---

## L3b. The extractor's false positives are not symmetric across the corpora

Recall is characterised in L3; precision is not symmetric, and the asymmetry
runs one way. Two identifier classes resolve on the human side and cannot
resolve on the machine side at all: a declaration's own name, which is in
scope because extraction is at declaration scope (98.4% of mathlib
declarations), and the `lemma` keyword, which is a real mathlib declaration
(31.7%). Goedel proofs carry `lean_workbook_*` names that are not mathlib
declarations, and are written `theorem`, which is core syntax. Both are
removed before any reported figure; uncorrected, they inflated our human
premise vocabulary by 33.6% and left the machine vocabulary unchanged.

Two consequences we state rather than resolve. First, the corrected and
uncorrected premise sets disagree about the *sign* of the precision artifact
in the instrument reference line (−0.042 against +0.024): uncorrected, the
machine side looks less spurious and the artifact compounds the recall term;
corrected, it looks more spurious and offsets it. We keep the uncorrected term
in the reference line because correcting it lowers the bar our own hypothesis
must clear. Second, our keyword list is internally inconsistent — it excludes
`congr`, `ext` and `subst` but not `symm` and `trans`, which are also tactic
names that are also mathlib theorems. We leave that inconsistency in place and
report its size (1.2% of corrected human premise occurrences) rather than
extend the list after seeing which names flatter the result.

## L3c. Three known one-sided effects remain, and all three inflate the human side

Beyond the two artifacts removed in L3b, three asymmetries are left in place.
We list them together because they share a direction: each one makes the human
premise vocabulary larger, or the machine one larger, in the way that *shrinks*
the gap this paper reports. None of them can manufacture the result; correcting
any of them would widen it.

| left in place | measured size | why it is one-sided | effect on the gap |
|---|---|---|---|
| `symm` / `trans` unexcluded | 5,222 human occurrences against 14 machine; 2 vocabulary entries; 1.2% of corrected human premise occurrences | tactic names that are also mathlib theorems, so they resolve in mathlib source and essentially never in Goedel proofs | inflates human, **narrows** the gap |
| prefix-resolution asymmetry | 3.657 premises per proof resolved by prefix completion on the human side against 0.374 on the machine side, 9.8× | every Goedel proof carries the same fixed five-namespace header, so its prefix pool is shallow; a mathlib declaration sits in its own namespace with whatever its file opens | inflates human, **narrows** the gap |
| coverage counted over both hub layers | machine vocabulary 25.6% infrastructure against human 4.6%, 5.6× | the machine side loses proportionally more under a mathematical-layer restriction | restricting gives 89.6× rather than 69.8×, so both-layer counting **narrows** the gap |

`symm`/`trans` stay because extending a keyword list one name at a time after
seeing which names inflate a favourable result is the hazard L3b already
describes; the inconsistency is reported with its size instead. Prefix
resolution stays because it is legitimate resolution rather than
contamination — it follows from the corpora's namespace conventions, not from
our parser. Both layers are counted because vocabulary membership has no
layer-aggregation problem to fix, and restricting would answer a narrower
question (methods M6).

**The measured gap is therefore a conservative one.** Every uncorrected
asymmetry we have found runs against the hypothesis, so the reported 78,642 /
1,127, Jaccard 0.0129 and 98.7% human-only are floors rather than best cases.
This is worth stating precisely because the opposite pattern — a result
surviving only under the particular set of corrections its authors chose to
apply — is what a reviewer is checking for, and because it is the same
argument as L3b's: the corrections we *did* apply cost us a third of the
headline, and the ones we declined to apply would have paid us.

---

## L4. The corpora target different mathematics

Machine corpora (Lean Workbook, miniF2F, Numina-derived) target competition
statements; mathlib targets library development. `nlinarith` is the natural
tool for the former and rarely the right one for the latter, so part of the
tactic-mix difference in L1 is a property of the problem sets rather than of
the provers. The comparison is over the *shared premise vocabulary*, and
length- and area-matched where possible. No control available to us removes
this confound — the two below only narrow it — so it bounds what "machine
proofs concentrate on" can mean.

Two partial controls narrow it. Restricting the human corpus to the 42
top-level library regions the machine vocabulary occupies — an *area* match —
leaves 32,091 human premises against 1,127, a ratio of 28.5× rather than 69.8×,
with 96.8% of the restricted human vocabulary still untouched by any machine
proof. That fixes area but not *genre*: a mathlib theorem is general-purpose
infrastructure and a competition problem is a self-contained puzzle, and
namespace restriction does not equalise that. As an **exploratory, not
pre-registered** check on genre, mathlib's own `Archive/Imo` — 52 files, IMO
1959–2025, 508 human-written declarations, no `sorry` — draws 1,101 distinct
premises, against 193 (range 164–227 over 20 seeds) for the machine corpus
rarefied to the same 508 proofs: **5.7×**, the smallest gap of any design we
ran. Three caveats travel with it and none is removable at this scale. It is a
**lower bound**: 467 of the 508 declarations cite helper lemmas defined locally
in `Archive/`, 744 citation tokens in all, and the extractor cannot see them
because `Archive` is outside the published graph's build target — counting them
would put the ratio nearer 8.5×. For the same reason it is **not
extraction-audited**, since no explicit subgraph exists for these declarations
and the retention assertion of §M1 does not cover them. And 508 against 29,750
is handled by rarefaction rather than by the step- and class-matching used
elsewhere. We report it because we measured it: the alternative is to publish
only the four designs that give larger gaps while holding a smaller one back.

---

## L5. Centrality is technical utility, not mathematical depth

Following the graph publishers' Finding 3, no aggregate centrality number is
reported without separating language-infrastructure from mathematical hubs,
and we never infer "less mathematically deep" from "higher centrality" — that
inference is contradicted in print. Our layer partition is provenance-based
rather than prefix-based; the prefix rule is retained only as a logged
cross-check, having over-captured 2,929 genuine mathlib results.

We hit the same rule a second time, from an unexpected direction, and it cost
us a result. The graph release publishes a per-declaration `dag_layer`
documented as distance from primitives; we built a depth metric on it and
promoted the resulting gap to a stated counter-finding. The attribute is a
centrality proxy. Layer 0 holds 119,633 nodes of maximum in-degree 0 and the
top layer holds `Eq.refl`, `Set` and `LE.le`; the correlation with log
in-degree is +0.677, and 13.8% of nodes carry a silently truncated value. Read
correctly the gap is a statement about citation weight, not derivation length,
so the metric is withdrawn (methods M4) rather than reinterpreted. The general
caution is that Finding 3 applies to *derived columns whose names do not
mention centrality*, not only to in-degree: a pipeline can consume such a
column with no signal that its documented direction is wrong. The check that
catches it — correlate the attribute against in-degree, inspect its extremes —
is cheap, and we recommend it for any released structural attribute.

---

## L6. Scope

Single machine corpus analysed in depth (Goedel-LM/Lean-workbook-proofs,
29,750 proofs). Non-archival, 4 pages. H2 is a comparison of two
distributions, not a causal claim about model behaviour; we write "machine
proofs concentrate on", never "provers are biased toward".
