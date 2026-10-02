# Methods

Working text for the paper's Methods section. Everything here is written for
a reviewer who cannot ask us a question — MATH-AI has no rebuttal phase.
Companion to `paper/limitations.md`: this file states what we did and what
the numbers rest on; that file states what the design cannot support.

---

## M1. Extraction instrument and its measured residual

We extract premises from source rather than by elaboration, following
CSLibPremiseBench, because our object of study is the **explicit subgraph**
(Li et al., Def. B.2.4) — the source-visible layer that 74.2% of mathlib's
dependency edges do not belong to. Source-visible extraction is the correct
instrument for that object, not a compromise for it.

Extraction runs at **declaration scope** (statement + proof), because
`is_explicit` edges come from the elaborated term of the whole declaration:
scoping to the proof body alone drops premises that the statement carries
while leaving them in the denominator.

We report retention rather than gating on it. The instrument's residual is
characterised by running the *same* loose matcher at three scopes on the same
sample (n=187 located declarations, 2,988 mathematical-layer explicit targets):

| scope | retention |
|---|---|
| whole file | 0.7915 |
| declaration block (reachable bound) | 0.6948 |
| structurally unreachable per-declaration | 0.0967 |
| our extractor | **0.6124** |

**Efficiency against the bound a per-declaration instrument can actually
reach is 0.8815.** The 0.0967 gap is the fraction of mathematical explicit
targets that appear somewhere in the file but nowhere in the declaration that
depends on them; no per-declaration instrument can recover those, and whether
a premise name appears elsewhere in a file is a property of how mathlib
authors organise files rather than of our parser. Of the remaining residual,
89.5% is the definitional gap between resolving identifiers and substring-
matching names, 8.9% an over-broad keyword list, 1.6% comment-only occurrences.

## M2. Results structure: coverage is primary

The paper leads with **coverage overlap** and treats breadth as the one
secondary characterization. Depth was a third; it is withdrawn in M4 because
the published attribute it rested on proved to be a centrality proxy rather
than a derivation-length measure. The reason for the ordering is
methodological and we state it rather than leaving it implicit.

Coverage overlap is a direct count. It needs no standardization, no length
control, no imputation of a machine-side rate, and no transfer assumption. Of
everything we measure, it is the only quantity that has not moved under
methodological pressure:

| quantity | stability under our own checks |
|---|---|
| instrument reference line | 0.129 → 0.080 → −0.001 → 0.099 across recovery instrument and length axis |
| precision artifact | −0.014 or −0.192 depending on length axis (13×), and it changes SIGN under the M2.0 correction |
| `structural_breadth` per step | magnitude moves 4× across designs (−0.61 / −0.78 / −0.20); an apparent sign flip was a character-axis artifact |
| `depth_reach` | **withdrawn (M4)** — the published `dag_layer` attribute is a centrality proxy, not distance from primitives |
| **coverage overlap (Jaccard)** | **0.0129 full corpora → 0.0128 under common support** |

The restriction that reverses or destroys every other comparison leaves
coverage essentially unchanged, because a count of distinct premises does not
depend on the length distribution it was collected over.

Two corrections to this section were made on 2026-08-19 and both are stated
rather than absorbed, because both change numbers this paper had already
written down. The vocabularies were inflated on the human side only (M2.0),
and the stability check had been cut on the character axis this paper rejects
elsewhere (M2.2).

### M2.0 Two one-sided extractor artifacts, removed

Extraction runs at declaration scope, so a declaration's statement is in
scope — and so is the declaration's own name. Nothing is its own explicit
dependency, so `theorem Foo.bar : ...` resolving `Foo.bar` is a false positive
by construction; our audit already counts it as spurious. It fires on **98.4%**
of mathlib declarations. It cannot fire on a Goedel proof, whose
`lean_workbook_*` name is not a mathlib declaration and never resolves.

Separately, `lemma` is a real mathlib declaration (`Mathlib.Tactic.Lemma`,
kind `definition`), so every mathlib source file that writes `lemma` resolves
it as a premise — **31.7%** of declarations. Every Goedel proof is written
`theorem`, which is core syntax and not a declaration.

Both are removed. Both shrink the human vocabulary and leave the machine
vocabulary bit-identical, so both move this paper's primary result against its
own hypothesis:

| | human vocabulary | machine vocabulary | Jaccard | human-only |
|---|---|---|---|---|
| uncorrected | 118,514 | 1,127 | 0.0089 | 0.9911 |
| **corrected** | **78,642** | **1,127** | **0.0129** | **0.9871** |

We report the uncorrected figures alongside rather than quietly replacing
them. One inconsistency is left in place and named: `symm` (4.6% of
declarations) and `trans` (2.8%) are tactic names that are also mathlib
theorems, and our keyword list excludes some tactic names but not these.
Extending that list one name at a time after seeing which names inflate a
favourable result is not a correction, so they stay, and their cost is
measured: two vocabulary entries and 1.2% of corrected human premise
occurrences.

### M2.1 The coverage result

Corpus-level premise vocabularies, full censuses — 70,086 human declarations
and 29,750 Goedel proofs:

| | human | machine |
|---|---|---|
| distinct premises used | **78,642** | **1,127** |
| premise occurrences | 437,062 | 61,897 |
| uses per distinct premise | 5.6 | 54.9 |

| scope | human proofs | machine proofs | Jaccard | intersection | human-only share |
|---|---|---|---|---|---|
| full corpora | 70,086 | 29,750 | **0.0129** | 1,014 | **0.9871** |
| common support (class × step) | 70,013 | 22,785 | **0.0128** | 1,009 | 0.9872 |
| matched 1:1 | 22,785 | 22,785 | 0.0360 | 774 | 0.9634 |

98.7% of the premises human mathlib proofs draw on are never touched by any of
29,750 machine proofs, and the machine corpus's entire working vocabulary is
1,127 declarations — about 0.4% of mathlib's 308,129. The machine side is
nearly a subset: 113 premises are machine-only, so there is almost no region
of the library the machine reaches that humans do not.

**The size objection is answered by measurement, not by argument.** A
vocabulary is a count over a corpus, and the human corpus is 2.4× larger, so
we measure how much of the gap corpus size alone can buy. Rarefying the human
corpus to exactly the machine corpus's size:

| human proofs sampled | human vocabulary |
|---|---|
| 3,504 (5%) | 11,493 |
| 17,522 (25%) | 35,910 |
| **29,750 — the machine corpus's size** | **49,601** |
| 70,086 (all) | 78,642 |

At equal n the ratio is **44×**. At 5% of our human corpus — 8.5× *fewer*
proofs than the machine corpus contains — the human vocabulary is still an
order of magnitude above the machine's full-corpus total. The 1:1 matched row
above makes the same control by construction, holding tactic class and proof
length equal as well as n, and leaves 96.3% of human premises untouched by any
machine proof.

This is the form in which the paper states its answer to the CFP's
humans-vs-machines question. "Narrower and more centrally concentrated"
invites an argument about how narrowness is measured. *Two proof populations,
both verified correct, sharing 1.3% of their premise vocabulary* does not.

It is also the sharpest available statement of H4: `pass@k` cannot see this,
and it is not a subtle statistical effect requiring a reader to trust our
controls.

### M2.2 The stability check, on the axis this paper actually defends

An earlier version of this section demonstrated coverage's stability against a
restriction to the 400–800 *character* band. That band retains 15.5% of the
human corpus and 14.3% of the machine corpus, and it is cut on the axis M3.1
rejects as substantially a formatting control. The stability check is
therefore redone on the common-support design of M5, which retains 99.9% and
76.6% on the wrap-invariant axis: **Jaccard 0.0129 → 0.0128**, human-only
0.9871 → 0.9872. Coverage is stable under the restriction that matters, and
the earlier demonstration was made on weaker evidence than the one available.

**Directly stated caveats.** Both vocabularies are measured through our
extractor, so both are lower bounds; the ratio carries the claim, and premises
we fail to recover cannot *add* to the machine vocabulary. And the corpora
target different problems — the confound of CLAUDE.md §5 — so this is a
property of the released corpora, not of provers in general. It remains the
case that a released corpus of 29.7K verified proofs exercises 0.4% of mathlib.

### M2.3 A quarter of the machine vocabulary is not mathematics

The vocabularies of M2.1 are counted over both of Li et al.'s hub layers. Split
by layer, the two corpora are not drawing on the same *kind* of library:

| | vocabulary | infrastructure | mathematical |
|---|---|---|---|
| human | 78,642 | 3,579 (**4.6%**) | 75,063 (95.4%) |
| machine | 1,127 | 289 (**25.6%**) | 838 (74.4%) |

**The machine vocabulary is 5.6× more infrastructure-weighted than the human
one.** This is reported as a result rather than as a basis note, for the same
reason M5's excluded region is: it is a property of the released corpus that
`pass@k` cannot see, and it says something the headline count does not. The
machine corpus's *mathematical* working vocabulary is 838 declarations —
0.27% of mathlib's 308,129, against the 0.4% that the both-layer count gives.

Nothing here is a centrality claim, and Li et al.'s Finding 3 is not engaged:
this is a count of set members per layer, not an aggregate score over two
populations that mean different things, and we do not read "more
infrastructure" as "less mathematically deep" — that inference is the one
their paper contradicts.

**It is the same failure mode as H2c, seen at the level of vocabulary rather
than of proofs.** H2c is a statement about corpus mass: `arith` × 0–2 tactic
steps is 23.1% of the Goedel corpus and 0.02% of mathlib. The layer split is a
statement about what the corpus's premise vocabulary consists of, and the two
line up — a corpus whose mass is short automation calls has a vocabulary
weighted toward the layer that automation calls resolve against, while a
library built by proving results from results does not. We report the
association and stop there: we have not measured which premises the degenerate
cell contributes, so this is not offered as a mechanism, and the wording stays
descriptive of the two corpora per CLAUDE.md §3.

The direction matters for how the primary result is read. Both-layer counting
is the *conservative* basis — restricting to the mathematical layer moves the
ratio from 69.8× to 89.6× and human-only from 98.7% to 99.0% (M6). The layer
composition is the reason: the machine side loses proportionally more under
the restriction than the human side does.

## M3. The instrument reference line

Both corpora are measured with the same instrument, but the instrument's
blind spot is not the same size on both — and it displaces structural metrics
in H2a's own predicted direction, because unrecovered premises make a proof
look structurally narrower. Every H2 figure therefore carries a **reference
line**: where a purely instrumental effect would land. H2a counts as supported
only if the observed gap clearly clears it.

(H2 was restated on 2026-08-22 — coverage, the since-withdrawn depth
counter-finding, and the degenerate-cell failure mode. Definitions in
CLAUDE.md §3; the restatement is recorded in
`notes/changes/2026-08-22-h2-restatement.md`. The reference line bears on
H2a and on the secondary characterizations of M4; it is not what adjudicates
H2b, whose mechanical checks are its own.)

The reference line is a difference of two directly standardized rates,

  D_m = Σ_s w_s^machine · r_s − Σ_s w_s^human · r_s,

where r_s is a human-measured per-stratum miss rate and w_s is each corpus's
censused share of stratum s. Machine miss rates cannot be measured without
elaborating machine proofs, so only the **mix** differs between the two terms.
That transfer assumption is load-bearing and is stated in Limitations (L1).

### M3.1 Stratification must include proof length — measured on the right axis

Our first stratification used tactic class alone. It should not be trusted,
and neither should a length control applied on the wrong measure of length. We
report both corrections, because the second reverses the first.

Scope loss is monotone in declaration length **within every tactic class**
(for `arith`, 0.415 → 0.078), and that within-class swing exceeds every
between-class difference, so the tactic partition is substantially a length
proxy. Length control is therefore mandatory (CLAUDE.md §5).

**But length must be measured comparably.** mathlib source is hand-wrapped
near 100 columns and carries docstrings; a Goedel `full_proof` is generated
and formatted differently. Counting tactic invocations — one fixed vocabulary,
one matcher, applied to both corpora after identical comment stripping — is
invariant to both. The two measures do not agree about whether the corpora are
comparable at all:

| axis | corpus overlap coefficient |
|---|---|
| characters | **0.215** |
| tactic steps | **0.856** |

| | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|
| human, tactic steps | 1 | 1 | 2 | 5 | 10 |
| machine, tactic steps | 1 | 1 | 3 | 6 | 12 |

The apparently near-disjoint length distributions are largely a formatting
difference. On a structural measure the corpora overlap 86%.

Joint standardization on (tactic class × length bin), n=7,531 human
declarations, both mixes censused:

| axis | class only | length only | class × length | 95% CI |
|---|---|---|---|---|
| tactic steps | +0.0748 | −0.0067 | **+0.0986** | (0.068, 0.126) |
| characters | +0.0748 | −0.0924 | +0.0051 | (−0.020, 0.029) |

**On the defensible axis the instrument artifact survives length control
almost intact**, strengthening slightly from +0.075 to +0.099. On characters
it appears to vanish. We report both and use the step axis, because the axis
choice was settled by the overlap measurement above rather than by preference,
and because the direction is against interest: the step axis makes the
artifact larger and so raises the bar our own hypothesis must clear.

### M3.2 The reference line is three numbers, not a five-class average

The class-only standardization presents as a five-stratum average. It is not
one, and a reviewer who works this out unaided will discount everything built
on it, so we state it directly.

Decomposing each side's total instrument penalty by stratum contribution
(w_s × Δr_s), for the instrument change that produced the class-only figure:

| stratum | human contribution | machine contribution |
|---|---|---|
| `none` | **+0.1128 (53.2%)** | +0.0085 |
| `simp` | +0.0946 (44.7%) | +0.0363 |
| `arith` | +0.0010 (0.5%) | **+0.1128 (69.2%)** |
| `other` | +0.0031 | +0.0034 |
| `decide` | +0.0004 | +0.0020 |
| **total** | **+0.2119** | **+0.1630** |

Two strata (`none`, `simp`) account for 97.9% of the human side; one stratum
(`arith`) accounts for 69.2% of the machine side; and those strata barely
overlap between corpora — `arith` is 76.4% of the machine mix and 0.7% of the
human mix, `none` is 53.4% of the human mix and 4.0% of the machine mix.

The consequence is that the reference line is far more sensitive to three
numbers than a five-class standardization appears to be. Its robustness is
the robustness of `none`'s human rate, `simp`'s human rate, and `arith`'s
transfer to a machine population roughly 100× larger — not the robustness of
an average over five strata. This is also why the length control in M2.1
moves the figure so violently: a construction resting on three numbers has no
internal averaging to damp a correction to any one of them.

### M3.3 The precision artifact compounds rather than offsets

Recall and precision displace structural metrics in *opposite* directions: a
missed premise makes a proof look narrower, a spurious one makes it look
broader. They could have cancelled. They do not.

Machine proofs have no ground-truth premise set, so the machine spurious rate
is imputed, by two independent standardizations of the human rate:

| route | imputed human | imputed machine | gap |
|---|---|---|---|
| tactic class | 0.4848 | 0.4009 | **−0.0839** |
| resolution mechanism | 0.4377 | 0.4282 | −0.0094 |

Both are negative — the machine side is *less* spurious, so it looks narrower
still, and the precision artifact **compounds** the recall artifact rather
than offsetting it.

**We report both routes and use the class route.** The mechanism route's
per-stratum spread is only 0.036 (exact 0.4216 vs prefix 0.4578); a
stratifier that barely separates its strata cannot produce a large
standardized difference regardless of how different the two mixes are, so its
small gap is *uninformative* about the artifact's size rather than reassuring
about it. The class route's spread is 0.127, which tracks real variation. The
cost of that choice is explicit — the class route transfers a human rate onto
a machine mix that is 76.4% `arith` — but choosing the larger artifact raises
the bar H2a must clear, so the transfer risk and the choice push the same way.

**The sign of this term depends on the M2.0 correction, and we report both.**
The rates above are measured on premise sets that still contain the two
one-sided artifacts. Recomputed on corrected sets over a full census, the
class-route gap is **+0.0235** rather than −0.0417 on the same basis: the
machine side becomes *more* spurious, and the precision artifact offsets the
recall one instead of compounding it. The flip is compositional — the
correction cuts `none` 0.270 → 0.103 and `simp` 0.342 → 0.216 but `arith` only
0.241 → 0.175, against mixes of 53.4% `none` (human) and 76.4% `arith`
(machine). We keep the uncorrected term in the reference line because
correcting it *lowers* the bar our own hypothesis must clear, and report the
corrected value as a sensitivity row.

One directly measured quantity underlies the machine side without any ground
truth: the **resolution mechanism mix** is 81.7% exact / 18.3% prefix for
machine proofs against 55.7% / 44.3% for human ones. This follows from the
released corpus rather than from our parser — every Goedel proof carries the
same five-namespace header, so its prefix pool is fixed and shallow, while a
mathlib declaration sits in its own namespace with whatever its file opens.

**Combined reference line.** Both terms length-controlled, on both axes:

| axis | recall | precision | combined | overlap coef. | machine mass extrapolated |
|---|---|---|---|---|---|
| tactic steps | +0.0986 | +0.0142 | **0.113** | 0.856 | 0.241 |
| characters | +0.0051 | +0.1917 | 0.197 | 0.215 | 0.011 |
| uncontrolled | +0.0748 | +0.0839 | 0.159 | — | — |

The two axes disagree about the precision term by 13× and in opposite
directions from a pre-registered prediction, which we report rather than
resolve. Two caveats travel with these numbers and are stated wherever they
appear. First, the components do not share a denominator — miss rate is over
explicit targets, spurious rate over resolved premises — so the sum is an
approximation of the right sign and magnitude, and the per-metric simulation
applies the two rates separately. Second, and more seriously, neither axis
gives a trustworthy combined value, for the reason developed in M5.

## M4. Depth is withdrawn; breadth is the one secondary characterization

**Depth reach is withdrawn from this paper's claims.** Earlier versions
reported it as a stated counter-finding — machine premises reaching further
from the primitives than human ones — and defended that reversal through two
pre-registered mechanism tests. The finding is withdrawn because the attribute
it rests on does not measure what the metric assumed.

`dag_layer`, the per-declaration attribute published with the dependency graph
and read verbatim by our depth metric, is documented as distance from
primitives. It does not behave that way. Layer 0 contains 119,633 nodes whose
maximum in-degree is 0 — uncited leaves, not axioms — while the highest layer
holds `Eq.refl` (69,580 citations), `Set`, `LE.le` and `Eq.mpr`. Across the
graph the attribute correlates +0.677 with log in-degree. A high `dag_layer`
marks heavily-cited foundational infrastructure and a low one marks an uncited
leaf, which is the opposite of the reading the metric was built on. The column
is also silently truncated: 42,520 nodes (13.8%) are never fully propagated,
and 36,788 of them carry a partial value indistinguishable from a completed
one.

**This makes the quantity a centrality proxy rather than a derivation-length
measure, and so unusable for the claim it was promoted to support.** Read
correctly, the gap does not reverse our hypothesis at all — it says machine
proofs concentrate on more heavily-cited infrastructure, which points the same
way as the coverage result and is a centrality statement, not a depth one.
Reporting it as a depth finding would infer mathematical shallowness or reach
from a centrality-like quantity, which is precisely the inference Li et al.'s
Finding 3 rules out. We therefore withdraw the metric rather than reinterpret
it: a quantity discovered to measure something other than its name, after the
comparison was seen, cannot be re-pointed at a different claim within the same
paper without becoming a researcher degree of freedom.

**This is a second independent instance of Finding 3, on a different
structural quantity.** Li et al. established it for in-degree centrality; we
find the same failure in the published layer attribute, which is not obviously
a centrality measure and is documented as a depth one. We report it as a
caution about the released graph's derived columns rather than as a result:
a source-visible pipeline can consume such a column without any signal that
its documented direction is wrong, and the check that catches it — correlating
the attribute against in-degree and inspecting its extremes — costs very
little.

All depth figures previously reported here, and the mechanism tests built on
them, are withdrawn with the metric. What survives is the negative
methodological finding above.

**Structural breadth is reported with its limitation stated.** It counts
distinct Louvain communities touched, and that partition is degenerate for
this purpose: median community size is 1, and the five largest communities
hold 68% of the graph. Breadth is therefore coarse.

An earlier version of this section reported that its per-step form flips sign
between the full corpus (−0.80) and the overlap region (+0.04). That was a
character-axis artifact. On the tactic-step axis it does not flip: the gap is
−0.607 on the full corpora, −0.780 under common support and −0.201 matched
1:1. It is quoted with all three, because the magnitude still moves 4× across
designs even though the direction does not.

## M5. Common support, and why the primary analysis is matched

Direct standardization reweights; it does not refuse. Handed a stratum where
one corpus has most of its mass and the other has almost none, it returns a
number built from whatever fallback rate was supplied. That is the situation
here, and it is not a binning artifact:

**`arith` × 0–2 tactic steps is 23.1% of the machine corpus and 0.02% of
mathlib** — about 14 of 70,086 declarations. Single-step `nlinarith [...]`
proofs are roughly a quarter of the released machine corpus and essentially do
not occur in mathlib. More data does not fix this: the human population itself
contains ~14 such declarations. It survives the wrap-invariant axis, and it is
why 24.1% of the machine mix in the step-axis control has no usable human
rate.

**The primary analysis is therefore a length-matched, common-support
comparison**, not a standardized one. Restricting to (class × step) cells
where both corpora have adequate support **retains 99.8% of the human corpus
and 75.9% of the machine corpus** — measured at 0.9990 and 0.7659 when the
design was run, 21 of 25 cells supported. Matching is inexpensive because the human
side is 70,086 located declarations rather than an audit sample: even a thin
machine cell has thousands of human declarations to draw against, and the
binding constraint is the machine corpus's 29,750 proofs.

The standardized full-corpus figures are reported as a secondary robustness
row, on both axes, each printed next to its overlap coefficient and its
extrapolated mass so a reader can see how much of it is inference and how much
is reweighting.

**The excluded region is reported as a result, not as attrition.** That a
quarter of a released prover corpus consists of single-step arithmetic-solver
calls with no analogue in the human library is a finding about the corpora,
and it speaks directly to the CFP's question about characteristic failure
modes. Every claim about "the machine corpus" after matching is a claim about
its non-degenerate 76%, and is worded that way throughout.

## M6. What the explicit subgraph does and does not license

"Spurious" is measured against the explicit subgraph, and `is_explicit` is an
elaborator property rather than a statement about whether a declaration
depends on a name. Splitting the human spurious set against the full 8.4M-edge
graph: of 8,167 spurious resolutions, 3,116 (38.2%) are real dependencies
carrying no explicit edge and 5,051 (61.8%) have no dependency of any kind.
The genuine false-positive rate is therefore 0.271, not the 0.438 measured
against the explicit subgraph alone.

**This correction is available on the human side only** and we do not present
it as symmetric. It requires looking a declaration up in the mathlib
dependency graph; machine proofs target competition statements and have no
node in that graph. The machine rate remains imputed from the *uncorrected*
human rate, so every gap in M3.3 is computed on the uncorrected basis on both
sides deliberately, and the 0.271 figure is never applied to the machine side.

Following Li et al.'s Finding 3, no aggregate centrality figure is reported
without separating the language-infrastructure and mathematical-infrastructure
hub layers, and we do not infer mathematical depth from centrality — that
inference is contradicted in print. All miss and spurious rates above are on
the mathematical layer.

**That restriction applies to the layer-sensitive metrics, not to coverage,
and the difference is not a lapse.** Li et al.'s rule is about *centrality
interpretation*: an aggregate centrality number mixes two hub populations
whose high scores mean different things, so the aggregate has no single
reading and must be split before it can be interpreted at all. Miss and
spurious rates inherit that problem, because they are rates over targets whose
weight is centrality-like — which is why they are reported on the mathematical
layer alone.

Coverage does not inherit it. Coverage asks what a prover draws on, and
vocabulary membership is a set-membership question with no aggregation step:
a premise is in a corpus's vocabulary or it is not, and that fact does not
change meaning depending on which layer the premise sits in. Restricting the
question to the mathematical layer would not remove an interpretive ambiguity;
it would answer a different and narrower question — what a prover draws on
*within the mathematics*, discarding the observation that a quarter of the
machine vocabulary is not mathematics. So coverage is reported over both
layers, and the restricted figure is reported beside it:

| basis | human vocab | machine vocab | ratio | Jaccard | human-only |
|---|---|---|---|---|---|
| **both layers — reported** | **78,642** | **1,127** | **69.8×** | **0.0129** | **0.9871** |
| mathematical layer only (robustness) | 75,063 | 838 | 89.6× | 0.0101 | 0.9899 |
| layer composition (infrastructure share) | 4.6% | **25.6%** | 5.6× | — | — |

**The reported basis is the weaker one.** Restricting to the mathematical
layer *strengthens* every coverage figure — 69.8× becomes 89.6×, 98.7%
human-only becomes 99.0% — because the machine vocabulary is 5.6× more
infrastructure-weighted than the human one and loses proportionally more under
the restriction. Reporting over both layers is therefore the conservative
choice rather than a convenient one, and the two bases are stated together so
that the mismatch between this section's basis and the primary result's is
visible and priced rather than latent. The composition gap is not only a
robustness control; it is a finding in its own right, and it is reported as
one in M2.3.
