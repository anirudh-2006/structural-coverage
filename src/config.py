"""Central configuration. No magic strings elsewhere in the codebase."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"

# --- Pinned data sources -------------------------------------------------
# Every revision below MUST be pinned and reported in the paper.

MATHLIB_GRAPH_REPO = "MathNetwork/MathlibGraph"
MATHLIB_GRAPH_REVISION = "8c706461fe266802197b62af324de12a3f1aa7fb"
MATHLIB_COMMIT = "534cf0b"     # 2 Feb 2026, per arXiv:2604.24797
# Full SHA resolved against leanprover-community/mathlib4; the 7-char form in
# the paper does not resolve via the GitHub API. Committed 2026-02-02T21:52:49Z.
MATHLIB_COMMIT_FULL = "534cf0b8f5267c3f20bf52f932ad5f9834187c35"
MATHLIB_REPO_URL = "https://github.com/leanprover-community/mathlib4.git"

GOEDEL_LEAN_WORKBOOK = "Goedel-LM/Lean-workbook-proofs"
GOEDEL_REVISION = "b731852af8d8ab11498fda27bce9020738c01c59"

DEEPSEEK_PROVER_V1 = "deepseek-ai/DeepSeek-Prover-V1"
DEEPSEEK_REVISION = None       # TODO: pin at E4, not needed for the audit

# --- Data layout ---------------------------------------------------------
# The graph repo ships TWO edge files with identical headers. `edges.csv`
# (753MB, 10.9M edges, 633,364 nodes) is the FULL LEAN ENVIRONMENT including
# core; `mathlib_edges.csv` is the mathlib-scoped graph whose counts match
# arXiv:2604.24797. Loading the wrong one silently changes every number in
# the paper, so only the correct paths are named here.

MATHLIB_GRAPH_DIR = DATA / "mathlib_graph"
DECL_EDGES_CSV = MATHLIB_GRAPH_DIR / "mathlib_edges.csv"
DECL_NODES_CSV = MATHLIB_GRAPH_DIR / "v2" / "declaration" / "nodes.csv"
DECL_METRICS_CSV = MATHLIB_GRAPH_DIR / "v2" / "declaration" / "metrics.csv"
TACTIC_USAGE_NDJSON = MATHLIB_GRAPH_DIR / "tactic_usage.ndjson"
GRAPH_SUMMARY_JSON = MATHLIB_GRAPH_DIR / "v2" / "summary.json"

MATHLIB_SRC = DATA / "mathlib_src"

# Extraction is the expensive step in every downstream analysis: one pass over
# 70,086 located mathlib declarations plus 29,750 Goedel proofs. The census
# cache holds the extracted premise sets so slicing, matching and rarefaction
# are cheap and always read the SAME extraction. Under `data/`, so gitignored
# and never hand-edited (CLAUDE.md §6).
CENSUS_CACHE = DATA / "census_cache"

# Ground truth for load-time assertions, from v2/summary.json. If a load
# disagrees with these, the wrong edge file is being read.
EXPECTED_DECL_NODES = 308_129
EXPECTED_DECL_EDGES = 8_436_366
EXPECTED_EXPLICIT_EDGES = 2_178_534

# --- Gates ---------------------------------------------------------------
# See CLAUDE.md §2. These are assertions, not aspirations.
#
# The Aug 21 gate is RELATIVE, not absolute. Decided 2026-08-13 after the
# ceiling analysis; see notes/decisions.md.
#
# `is_explicit` means "occurs in an explicit argument position of the
# ELABORATED TERM" (lean-training-data `premises`, the `*` marker), not
# "written by a human". A strict upper bound built by matching premise names
# anywhere in the whole source file recovers only 0.819 of mathematical-layer
# explicit edges, so an absolute 0.90 is unreachable by construction — that
# ceiling is a property of Lean's elaborator, not of our parser.
#
# Gating on efficiency against the measured ceiling tests the instrument
# instead. It is a demanding bar: it permits 5% instrument loss, where the
# original absolute gate permitted 10%.
AUDIT_EFFICIENCY_THRESHOLD = 0.95   # retention / ceiling, on the maths layer
CEILING_MATHEMATICAL = 0.8193       # measured n=495, results/ceiling_analysis.csv
# Implied absolute floor: 0.95 * 0.8193 = 0.778.
AUDIT_RETENTION_THRESHOLD = AUDIT_EFFICIENCY_THRESHOLD * CEILING_MATHEMATICAL

AUDIT_SAMPLE_SIZE = 200
AUDIT_CEILING_SAMPLE_SIZE = 50     # crude upper-bound pass, no parser involved

# --- Sample sizes of the COMMITTED runs ----------------------------------
# These two were passed on the command line for the runs whose CSVs are in
# results/, while the module defaults were smaller. Running the documented
# default therefore regenerated different, plausible-looking numbers — found
# by the 2026-09-04 clean-room reproduction, which could not reproduce
# results/ceiling_analysis.csv or results/length_controlled_*.csv until the
# recorded sizes were supplied by hand. They are named here so that
# regenerating from a clean checkout reproduces the committed artifacts, per
# CLAUDE.md §8 (constants live in config, not in prose) and §6 (every figure
# regenerates from script + config + seed).
#
# CEILING_SAMPLE_SIZE reproduces results/ceiling_analysis.csv byte-for-byte
# and is the n behind CEILING_MATHEMATICAL = 0.8193 above (see its comment,
# "measured n=495"). AUDIT_CEILING_SAMPLE_SIZE stays at 50 and is unused by
# default; it is retained because the gate discussion above refers to it.
CEILING_SAMPLE_SIZE = 495

# LENGTH_CONTROL_CLASS_CAP reproduces results/length_controlled_cells.csv and
# results/length_controlled_reference.csv, i.e. the n=7,531 joint
# standardization the paper reports in M3.1. Recorded in
# notes/changes/2026-08-17-length-axis-correction.md ("n=7,531, seed
# 20260812, cap 2,500"). It is DELIBERATELY NOT `tactic_strata.CLASS_SAMPLE_CAP`
# (400): that cap is shared with tactic_strata and arith_sensitivity, whose
# committed CSVs do reproduce at 400, so raising it there would change
# artifacts that are currently correct.
LENGTH_CONTROL_CLASS_CAP = 2_500

# --- The Aug 21 gate: option (d), decided 2026-08-16 ---------------------
# The threshold above has now been mis-specified twice — 0.90 absolute against
# a denominator whose LAYER was wrong, then 0.95 efficiency against a ceiling
# whose SCOPE was wrong (whole file vs declaration). Maximum attainable
# efficiency at declaration scope is ~0.878, so 0.95 is unsatisfiable, and
# re-deriving a threshold a third time after seeing 0.8815 is precisely the
# researcher-degrees-of-freedom hazard CLAUDE.md §6 exists to prevent.
#
# DECISION: drop the pass/fail framing. `tests/test_extraction_audit.py`
# reports retention with its scope decomposition and asserts only that the
# audit is COMPUTABLE and STABLE. The paper defends the instrument on the
# characterised residual, not on a threshold.
#
# A permanently red suite stops being informative: once a failure is expected,
# every other failure in it gets ignored too. That is the real cost, and it is
# why this is a change in what the test asserts rather than a skip mark.
#
# AUDIT_EFFICIENCY_THRESHOLD and AUDIT_RETENTION_THRESHOLD are retained: they
# are still REPORTED, and `AuditResult.passes_gate` still computes, so the
# paper can state the bar the instrument does not clear and by how much.
AUDIT_GATE_IS_ASSERTED = False

# Recorded 2026-08-16 from the first full run (`204dd30`), n=187 located of
# 198. The stability assertion is a REGRESSION guard, not a quality bar — it
# fires if a code change moves the instrument, which is the thing a test can
# usefully catch here. The tolerance is deliberately loose enough that
# resampling noise cannot trip it and tight enough that a real parser
# regression will.
AUDIT_RETENTION_RECORDED = 0.6124
AUDIT_RETENTION_STABILITY_TOL = 0.03

# --- Metric parameters ---------------------------------------------------
# FROZEN once machine-corpus results exist. See CLAUDE.md §6.
# Any change after that date must be logged in notes/decisions.md.

CENTRALITY_DECILES = 10
LOUVAIN_RESOLUTION = 1.0
LOUVAIN_SEED = 20260812
LENGTH_CONTROL_BINS = [1, 2, 3, 5, 8, 13, 21, 34, 10_000]

# --- The two-layer hub split (arXiv:2604.24797 Finding 3) ----------------
# Aggregating across these makes centrality uninterpretable — always report
# them separately. This partition also defines the AUDIT GATE DENOMINATOR,
# so it is a frozen researcher degree of freedom under CLAUDE.md §6.
#
# Prefix matching is NOT the mechanism. It misses every root-level
# elaborator-inserted constant, and `kind` alone does not rescue it:
#
#   name              kind        in_degree   file_module
#   propext           axiom          23,226   (empty)
#   Eq.mpr            definition     62,942   (empty)
#   of_eq_true        theorem        48,801   (empty)   <- kind says "theorem"
#   funext            theorem        15,574   (empty)   <- kind says "theorem"
#   Classical.choice  axiom             169   (empty)
#   AddSemigroup.toAdd abbrev         6,499   Mathlib.Algebra.Group.Defs
#                                                       (is_instance=True)
#
# The reliable signal is PROVENANCE: every Lean-core constant has an empty
# file_module. See graph.load.split_hub_layers for the four rules.

# Rule 3: kernel-level kinds, generated rather than authored.
KERNEL_KINDS = frozenset({"axiom", "constructor", "recursor", "quotient"})

# Rule 4: compiler-generated name structure. Matched on generated-name
# markers only — never on mathematical namespaces.
GENERATED_NAME_MARKERS = (
    "._proof_", "._aux_", "._to_additive_", ".match_", ".eq_def",
    ".injEq", ".noConfusion", ".casesOn", ".recOn", ".sizeOf_spec",
    ".brecOn", ".below", ".ndrec", ".ofNat_toCtorIdx",
)

# Declarations authored in mathlib live under this file_module prefix.
MATHLIB_MODULE_PREFIX = "Mathlib."

# Retained as a CROSS-CHECK ONLY, not as the partition mechanism: assert the
# provenance-based split is a superset of what these prefixes catch, and log
# any divergence. Do not reintroduce this as the classifier.
INFRASTRUCTURE_NAMESPACE_PREFIXES = (
    "Eq", "HAdd", "HMul", "OfNat", "Nat.", "List.rec",
    "instDecidableEq", "instRepr", "Decidable",
)

# --- Miss classification (audit diagnostics) -----------------------------
# missed_elaborator_inserted vs missed_genuine cannot be decided per-edge
# without Lean. Proxy: typed_rate(t) = fraction of declarations that depend
# explicitly on t AND mention t in their source text. Computed from raw file
# text via the crude ceiling matcher, NOT from parser output, so a broken
# parser cannot manufacture "elaborator-inserted" labels.
TYPED_RATE_BACKGROUND_SIZE = 4_000
TYPED_RATE_THRESHOLD = None   # freeze from the histogram; None => no hard split

# Tactics that close a goal without naming its premises in source. Not an
# exclusion criterion — a stratification one. See CLAUDE.md §6.
AUTOMATION_TACTICS = frozenset({
    "simp", "simp_all", "omega", "ring", "ring_nf", "norm_num", "aesop",
    "decide", "linarith", "nlinarith", "positivity", "polyrith", "tauto",
    "field_simp", "bound",
})

# --- Tactic classes (supersedes the binary automation flag) --------------
# Decided 2026-08-13. A binary automation/none split leaves the confound
# INSIDE the automation stratum: the machine corpus is nlinarith-dominated
# (65.7% of Goedel proofs) while the human automation stratum is not, so the
# two "automation" populations are not the same population.
#
# The three named classes hide premises by different mechanisms, which is why
# they are expected to have different miss rates:
#
#   arith   - hands the goal to a solver over hypotheses; cites no library
#             lemma by name at all.
#   simp    - fires named simp-set lemmas, SOME of which appear in source as
#             `simp [foo]` and are therefore partially recoverable.
#   decide  - decision procedure over a fixed theory; the premises it uses
#             are largely kernel-level, not mathematical-layer.
#
# ring/ring_nf/field_simp/positivity/aesop/tauto/bound land in `other`. Note
# field_simp (19.0%) and ring_nf (17.9%) are non-trivial in the machine mix,
# so `other` is not a rounding-error stratum — it is reported, not folded in.
TACTIC_CLASSES = {
    "arith": frozenset({"nlinarith", "linarith", "polyrith"}),
    "simp": frozenset({"simp", "simp_all", "norm_num"}),
    "decide": frozenset({"omega", "decide"}),
    "other": frozenset({"ring", "ring_nf", "field_simp", "positivity",
                        "aesop", "tauto", "bound"}),
}
TACTIC_CLASS_NONE = "none"

# Proofs use several tactics, so the classes overlap. Standardization needs a
# PARTITION, so a proof is assigned to the first class here that it uses.
# Declared before the rates were measured, and ordered by how completely the
# class closes a goal without naming premises. The choice is arbitrary enough
# to matter, so analysis.tactic_strata reports the standardized estimate under
# ALL orderings as a sensitivity range; if that range is wide, the ordering
# is load-bearing and must be reported in the paper.
TACTIC_CLASS_PRECEDENCE = ("arith", "simp", "decide", "other")

# --- Proof length bins ---------------------------------------------------
# Added 2026-08-16. CLAUDE.md §5: "Control for proof length everywhere. Short
# proofs mechanically use fewer, more common premises."
#
# The tactic partition turned out to be substantially a LENGTH proxy:
# declaration-scope scope-loss is monotone in block length within every class
# (arith 0.415 -> 0.078 across these bins) and that within-class swing exceeds
# every between-class difference. Median block chars by class: arith 679,
# simp 349, decide 322, other 235, none 223. So standardizing on class alone
# silently standardizes on length, badly.
#
# Measured in CHARACTERS of the declaration block (statement + proof), which
# is the same object on both sides: the located mathlib block, and the Goedel
# `theorem ...` line onward with the corpus header excluded.
#
# Boundaries are round numbers on a log-ish scale, chosen to keep the `arith`
# stratum populated in every bin (31/97/110/91/77) since arith carries 76.4%
# of the machine mix. They were fixed BEFORE the joint rates were computed.
# They are a reporting grid, not a fitted control.
PROOF_LENGTH_BINS = ((0, 200), (200, 400), (400, 800), (800, 1_600), (1_600, None))

# Tactic-step bins — the WRAP-INVARIANT axis, and the PRIMARY one from
# 2026-08-16. `analysis.length_overlap` measured the two corpora's overlap
# coefficient at 0.215 on characters and 0.856 on tactic steps: the
# near-disjoint character supports are largely a formatting artifact of
# mathlib's hand-wrapped, docstring-carrying source versus Goedel's generated
# output. Any length control done on characters is therefore controlling
# substantially for formatting. Steps are the defensible axis; characters are
# retained as the sensitivity row.
PROOF_STEP_BINS = ((0, 2), (2, 4), (4, 8), (8, 16), (16, None))

# Minimum declarations in a (class x length) cell before its rate is used
# directly. Below this the cell falls back — length bin first, because length
# is the dominant axis — and every collapse is reported, never silent.
LENGTH_CELL_MIN_N = 30

# --- Tactic-step count: a WRAP-INVARIANT length measure ------------------
# Added 2026-08-16. Character counts are not obviously comparable across the
# two corpora: mathlib source is hand-wrapped near 100 columns and carries
# docstrings, while a Goedel `full_proof` is generated and formatted
# differently. If the near-disjoint length distributions were an artifact of
# formatting rather than of proof structure, every length-controlled number
# would be measuring the wrong thing.
#
# Counting TACTIC INVOCATIONS is invariant to wrapping and (after
# `audit.strip_noise`) to docstrings and comments. It is a structural measure
# of proof size, applied with the same vocabulary and the same matcher to
# both corpora — the same discipline as the automation-tactic strata.
#
# Vocabulary is deliberately broad and fixed BEFORE the counts were computed.
# It is a size proxy, not a taxonomy: a tactic missing from this list costs a
# little sensitivity on both sides equally, which is why comparability
# matters more here than completeness.
COUNTABLE_TACTICS = frozenset({
    # structural
    "intro", "intros", "apply", "exact", "refine", "rintro", "rcases",
    "obtain", "cases", "induction", "constructor", "use", "have",
    "show", "let", "set", "suffices", "calc", "conv", "specialize", "subst",
    "revert", "rename_i", "by_cases", "by_contra", "contrapose", "exfalso",
    "left", "right", "ext", "funext", "congr", "convert", "symm", "trans",
    # rewriting / normalisation
    "rw", "rwa", "erw", "simp", "simp_all", "simpa", "simp_rw", "norm_num",
    "norm_cast", "push_cast", "exact_mod_cast", "field_simp", "ring",
    "ring_nf", "abel", "group", "unfold", "delta", "change",
    # closing / automation
    "omega", "decide", "linarith", "nlinarith", "polyrith", "positivity",
    "gcongr", "bound", "aesop", "tauto", "trivial", "rfl", "assumption",
    "contradiction", "norm_fin", "finiteness", "measurability", "continuity",
    "fun_prop", "nontriviality", "infer_instance",
})

# --- H2 instrument reference line ----------------------------------------
# Set 2026-08-13. Basis of the multiplier REVISED 2026-08-14, still before
# E3 and before any machine-side structural metric exists. See
# notes/decisions.md.
#
# The instrument alone displaces H2's metrics in H2's own predicted direction:
# unrecovered premises make a proof look structurally narrower. So every H2
# figure carries a REFERENCE LINE showing where a purely instrumental effect
# would land, and H2 counts as supported only if the observed gap clearly
# clears it.
#
# UNITS. The reference line is NOT the premise-fraction scalar below. H2's
# metrics are Gini / breadth / depth-reach. Per metric m, the displacement
# D_m is computed by simulation: take the HUMAN corpus, delete premises at
# INSTRUMENT_MISS_RATE_BY_CLASS weighted by the MACHINE class mix, recompute
# m, and take the displacement from the undeleted human value. The simulation
# is itself swept over the 24 precedence orderings, giving D_m a point
# estimate, a bootstrap CI, and its own ordering BAND. The thresholds below
# are RATIOS applied to D_m, never absolute numbers in premise-fraction
# units. See analysis.instrument_reference (E3).
#
# Decision rule, per metric. RE-SPECIFIED 2026-08-17. Three outcomes:
#
#   supported     the 95% CI on the observed gap lies ENTIRELY ABOVE
#                 band_top(D_m) -- the top of D_m's own precedence band.
#   inconclusive  observed gap > D_m(point estimate) but its CI overlaps
#                 band_top. Reported as "not separable from the instrument".
#                 This is NOT evidence against H2 and must not be written up
#                 as one.
#   unsupported   observed gap <= D_m(point estimate).
#
# WHY THE MULTIPLIER WAS RETIRED (2026-08-17). The old rule required
# `observed >= 2.0 * D_m(point)`. A multiplicative bar on a point estimate is
# only meaningful while that point estimate is bounded away from zero, and
# D_m is computed PER METRIC by simulation -- there is no guarantee any given
# metric's D_m is large. When the 2026-08-16 character-axis run put the
# premise-fraction D_m at -0.001, `2.0 x D_m` would have passed literally any
# observed gap, including a negative one. That the figure was itself an
# artifact (see the reference line below) does not rescue the rule: a criterion
# that degenerates when the artifact it corrects for happens to be small is
# the wrong shape, and the right time to fix its FORM is now, before any E3
# result exists to be judged by it.
#
# The replacement is scale-free in the right way. It says: the observed
# difference must be separable from the instrument artifact including that
# artifact's own worst-case ordering, at 95% confidence. It cannot degenerate
# as D_m -> 0 -- it just becomes a test against ~0, which is exactly correct,
# because if the instrument really displaces nothing then any reliably
# non-zero gap is real. And it cannot be gamed by a large D_m either: a big
# artifact makes band_top big and the bar correspondingly high.
#
# It is also STRICTLY STRONGER than the old rule's second clause, which it
# absorbs, so nothing that passed the CI condition before fails it now.
H2_SUPPORT_CRITERION = "ci_above_band_top"
H2_INSTRUMENT_MARGIN_FACTOR = None   # RETIRED 2026-08-17 -- see above
H2_MARGIN_BASIS = None               # RETIRED with the multiplier
H2_BOOTSTRAP_RESAMPLES = 2_000
H2_BOOTSTRAP_CI = 0.95

# Measured 2026-08-13 by analysis.tactic_strata, results/instrument_reference.csv.
# RE-DERIVED 2026-08-16 against the real extractor — see below.
# Human per-class miss rates standardized onto each corpus's class mix, both
# mixes censused with the same instrument. THESE ARE THE DELETION RATES the
# per-metric simulation uses; the scalar below is their summary, in
# premise-fraction units, and is NOT itself plottable on a Gini axis.
#
# RECOVERY INSTRUMENT: the real extractor (extract.audit.extract at
# declaration scope, loose credit), NOT the whole-file ceiling matcher.
# The 2026-08-13 values were cut with `ceiling.name_or_suffix_occurs` against
# the whole FILE, because no extractor existed then. E3 runs on the extractor,
# so rates cut any other way parameterize the reference line with a blind spot
# the analysis never has. The SCALAR is a basis correction rather than a §9
# unfreezing — it moved 1.61x, inside the 2x trigger — but TWO of the
# per-class rates trip §9 on their own and are re-derived under
# notes/changes/2026-08-16-none-decide-unfrozen.md.
#
#   class     ceiling matcher   real extractor    delta    ratio
#   arith          0.3448           0.4925       +0.1477   1.43x
#   simp           0.3025           0.5166       +0.2140   1.71x
#   decide         0.1264           0.3253       +0.1989   2.57x  <- §9 UNFROZEN
#   other          0.4073           0.6135       +0.2062   1.51x
#   none           0.1034           0.3146       +0.2112   3.04x  <- §9 UNFROZEN
#
# WHY THE REFERENCE SHRANK RATHER THAN GREW (0.129 -> 0.080) even though every
# class got MISSIER. The extractor's additional blind spot is close to a
# constant additive +0.20..+0.21 in every stratum EXCEPT `arith` (+0.148) —
# and `arith` is 76.4% of the machine mix against 0.7% of the human mix. So
# the extra miss lands mostly on the HUMAN side of the standardization and
# partly cancels in the difference. Weighted: +0.163 machine, +0.212 human,
# net -0.050, which reproduces the observed move. The gap is a DIFFERENCE of
# standardized rates, so a near-uniform penalty is invisible to it by
# construction; only the arith-specific shortfall survives.
#
# THE MOVE FAVOURS H2, SO IT GETS A SENSITIVITY CHECK. Shrinking the reference
# line lowers the 2.0x support threshold from 0.258 to 0.160 — H2 gets easier
# to support. analysis.arith_sensitivity tests the account above three ways
# (results/arith_counterfactual_gap.csv and four sibling CSVs):
#
#   1. Force arith's penalty to the flat +0.20 the other strata show and
#      restandardize: the gap returns to +0.1197. So 81% of the entire
#      0.129 -> 0.080 move is the arith deviation alone (93% using the exact
#      non-arith mean of +0.2076). Essentially the whole favourable move
#      rests on ONE stratum's shortfall.
#   2. Mechanism hypothesis A, inline hint lists (`nlinarith [sq_nonneg ...]`
#      naming premises in source where simp-closed proofs do not):
#      FALSIFIED. arith hint-list recall 0.0131 vs simp 0.0274; hint lists
#      carry 2.4% of arith's recovered targets vs simp's 5.0%.
#   3. Mechanism hypothesis B, PROOF LENGTH: supported and partial. arith's
#      median declaration block is 679 chars vs simp 349 / other 235 /
#      none 223, and scope loss is monotone in block length within every
#      class (arith 0.415 -> 0.078 across the bins) — a larger swing than
#      any between-class difference. Standardizing onto the arith length mix
#      cuts the arith-simp scope gap 0.0731 -> 0.0450, so length accounts for
#      38% of it and a real class effect carries the rest.
#
# CONSEQUENCE — length control was then done, and it REMOVED THE EFFECT.
# See H2_INSTRUMENT_REFERENCE below and
# notes/changes/2026-08-16-length-controlled-reference.md. The class-only
# value of +0.080 is retained here only as the uncontrolled comparison; the
# rates in INSTRUMENT_MISS_RATE_BY_CLASS are NOT the reference line any more
# and must not be used to parameterize one. They remain the right per-class
# diagnostic and are what the A1 table reports.
#
# BASIS: `partition`, NOT `marginal`. results/miss_rate_by_tactic_class.csv
# carries both, under all three recovery instruments, and they are not
# interchangeable. It must be `partition` for UNITS reasons, not preference.
# These rates are applied to tactic_class_mix.csv, which is a PARTITION mix:
# each proof is assigned to exactly one class by TACTIC_CLASS_PRECEDENCE and
# both corpora's mixes sum to 1.0. Marginal rates are measured over
# OVERLAPPING populations — a proof using both omega and nlinarith counts in
# arith AND in decide — so multiplying them by disjoint shares double-counts
# every proof that uses several automation families, which is most of the
# machine corpus. The marginal rates are the right diagnostic ("how invisible
# is class X overall") and are what the A1 table in notes/decisions.md
# reports; they are not standardization-compatible.
# See notes/changes/2026-08-16-instrument-reparameterization.md.
INSTRUMENT_MISS_RATE_BY_CLASS = {
    "arith": 0.492,
    "simp": 0.517,
    "decide": 0.325,
    "other": 0.614,
    "none": 0.315,
}
# --- THE RECALL REFERENCE LINE, LENGTH-CONTROLLED ------------------------
# Re-derived 2026-08-16 on the CHARACTER axis, then CORRECTED 2026-08-17 onto
# the tactic-STEP axis. The correction reverses the 08-16 conclusion, so both
# are kept here and the reason is stated rather than the old row deleted.
#
# 2026-08-16 said: length control removes the recall artifact (D_m -0.001).
# 2026-08-17 says: it does not. That result was an artifact of measuring
# length in CHARACTERS. mathlib source is hand-wrapped near 100 columns and
# carries docstrings; a Goedel `full_proof` is generated and formatted
# differently. `analysis.length_overlap` measured the two corpora's overlap
# coefficient at 0.215 on characters against 0.856 on tactic steps -- so the
# "near-disjoint length supports" were largely a formatting difference, and
# controlling on characters was substantially controlling for formatting.
#
# Joint standardization on (tactic class x length bin), n=7,531 human
# declarations (cap 2,500 per marginal class), both mixes censused:
#
#   axis     overlap   class-only   length-only   JOINT     95% CI
#   steps     0.856      +0.0748      -0.0067   +0.0986   (0.068, 0.126)  <- PRIMARY
#   chars     0.215      +0.0748      -0.0924   +0.0051   (-0.020, 0.029)
#
# On the defensible axis the recall artifact SURVIVES length control almost
# intact (+0.0748 -> +0.0986; it strengthens slightly). Precedence band over
# the 24 orderings (0.0762, 0.1257), band_top/point = 1.28.
#
# 24 of 25 step cells carry their own rate; only `decide` collapses, and it is
# 1.0% of the machine mix and 0.2% of the human mix.
H2_INSTRUMENT_REFERENCE = 0.099     # joint, STEP axis, machine 0.5480-ish
H2_INSTRUMENT_REFERENCE_CI = (0.068, 0.126)      # 2000x, resampled within cell
H2_INSTRUMENT_REFERENCE_BAND = (0.076, 0.126)    # 24 precedence orderings
H2_INSTRUMENT_REFERENCE_AXIS = "steps"
H2_INSTRUMENT_REFERENCE_IS_PROVISIONAL = True

# Sensitivity and superseded rows. NOT reference lines -- do not parameterize
# anything with them.
H2_INSTRUMENT_REFERENCE_CHAR_AXIS = 0.005        # the 2026-08-16 headline
H2_INSTRUMENT_REFERENCE_CHAR_AXIS_CI = (-0.020, 0.029)
H2_INSTRUMENT_REFERENCE_CLASS_ONLY = 0.075
H2_INSTRUMENT_REFERENCE_LENGTH_ONLY = -0.007     # step axis
H2_INSTRUMENT_REFERENCE_LENGTH_ONLY_CHARS = -0.092

# Superseded 2026-08-16, retained so the paper can state the instrument's
# effect on its own reference line. Same design, ceiling-matcher recovery.
INSTRUMENT_MISS_RATE_BY_CLASS_CEILING = {
    "arith": 0.345, "simp": 0.303, "decide": 0.126, "other": 0.407,
    "none": 0.103,
}
H2_INSTRUMENT_REFERENCE_CEILING = 0.129
H2_INSTRUMENT_REFERENCE_CEILING_BAND = (0.085, 0.166)

# --- the PRECISION artifact, and the combined line -----------------------
# Measured 2026-08-16 by analysis.spurious_symmetry.
# See notes/changes/2026-08-16-spurious-symmetry.md.
#
# The audit gates on recall and never on the 1,146 spurious resolutions. Not
# gating is right — tuning precision after seeing the gate number is the §6
# hazard — but precision enters H2 the same way recall does, with the sign
# flipped:
#
#   a MISSED premise    makes a proof look structurally NARROWER
#   a SPURIOUS premise  makes a proof look structurally BROADER
#
# So the two artifacts could have cancelled. THEY DO NOT. The machine side is
# imputed to be LESS spurious than the human side under both routes, which
# narrows it further and COMPOUNDS the recall artifact:
#
#   route                        imputed human   imputed machine     gap
#   class standardization             0.4848           0.4009      -0.0839
#   mechanism standardization         0.4377           0.4282      -0.0094
#
# The mechanism mix is a DIRECT measurement on both corpora, needing no ground
# truth: machine 81.7% exact / 18.3% prefix against human 55.7% / 44.3%. Every
# Goedel proof carries the same five-namespace header while a mathlib
# declaration sits in its own namespace, so the prefix pool is fixed and
# shallow on the machine side and variable and deep on the human side.
H2_INSTRUMENT_SPURIOUS_CLASS_ROUTE = -0.0839       # machine narrower — CHOSEN
H2_INSTRUMENT_SPURIOUS_MECHANISM_ROUTE = -0.0094   # machine narrower

# TIE-BREAK RESOLVED 2026-08-16 (author's call, CLAUDE.md §6): the CLASS
# route feeds the reference line. Reasoning, which goes in the paper next to
# the band rather than replacing it:
#
# The mechanism route's per-stratum spread is only 0.036 (exact 0.4216 vs
# prefix 0.4578). A stratifier that barely separates its strata cannot produce
# a large standardized difference no matter how different the two mixes are —
# so its small gap of -0.0094 is uninformative about the size of the artifact,
# not reassuring about it. The class route's spread is 0.127, which is a
# stratifier that actually tracks spurious variation, so its -0.0839 is a
# real signal about a real compositional difference.
#
# The cost of choosing it is explicit: the class route transfers a human rate
# onto a machine class mix that is 76.4% `arith`, which is the standing
# transfer objection. Choosing the larger artifact is the conservative
# direction for H2 — it raises the bar the hypothesis must clear — so the
# transfer risk and the choice push the same way, which is why this is the
# safe end to pick under uncertainty.
#
# BOTH ROUTES STAY VISIBLE IN THE PAPER. The band is reported; 0.0839 is the
# line H2 is judged against.
H2_SPURIOUS_ROUTE = "class"

# COMBINED displacement, in "how much narrower the machine looks for purely
# instrumental reasons" units. Both components carry the same sign, so they
# ADD; this is the line H2 must clear.
#
# RECOMPUTED 2026-08-17 with BOTH terms length-controlled, on both axes.
# The class route is the chosen spurious route (H2_SPURIOUS_ROUTE).
#
#   axis    recall    spurious   combined   overlap   machine mix in
#                                            coef.    collapsed cells
#   steps   +0.0986   +0.0142     0.113      0.856        0.241
#   chars   +0.0051   +0.1917     0.197      0.215        0.011
#   (uncontrolled, for reference: +0.0748 + 0.0839 = 0.159)
#
# *** NEITHER AXIS GIVES A TRUSTWORTHY COMBINED VALUE, AND THE REASON IS THE
# *** SAME ON BOTH: EXTRAPOLATION. This is stated here because the numbers
# *** above are individually quotable and individually misleading.
#
# On CHARS the supports are near-disjoint (overlap 0.215) so the joint
# standardization is extrapolating almost everywhere.
#
# On STEPS the supports overlap well in aggregate (0.856) but the joint mix
# does not: 24.1% of the machine mix sits in cells with no usable human rate,
# and 23.1 of those 24.1 points are ONE CELL -- `arith` x 0-2 tactic steps.
# That cell is 23.1% of the Goedel corpus and 0.02% of mathlib (about 14 of
# 70,086 declarations). Single-step `nlinarith [...]` proofs are a quarter of
# the machine corpus and essentially do not occur in mathlib.
#
# THAT IS NOT A SAMPLING LIMITATION AND MORE DATA WILL NOT FIX IT. The human
# population itself has ~14 such declarations. It is a genuine structural
# non-overlap between the corpora, it survives the wrap-invariant axis, and
# it means direct standardization has to invent a rate for a quarter of the
# machine corpus no matter how the bins are drawn.
#
# CONSEQUENCE FOR E3: the primary analysis must be a COMMON-SUPPORT
# comparison, not a standardized one. Restricting to cells with a usable
# human rate retains 99.8% of the human corpus and 75.9% of the machine
# corpus, and the excluded 24% is one nameable stratum that can be reported
# on its own terms. See paper/methods.md M4.
H2_INSTRUMENT_REFERENCE_COMBINED = 0.113          # steps axis; see caveat above
H2_INSTRUMENT_REFERENCE_COMBINED_CHARS = 0.197    # sensitivity
H2_INSTRUMENT_REFERENCE_COMBINED_UNCONTROLLED = 0.159
H2_INSTRUMENT_REFERENCE_COMBINED_BAND = (0.113, 0.197)
H2_COMMON_SUPPORT_RETAINED_HUMAN = 0.998
H2_COMMON_SUPPORT_RETAINED_MACHINE = 0.759

# The length-controlled SPURIOUS term, both axes. See
# notes/changes/2026-08-17-spurious-length-controlled.md and the
# pre-registered prediction alongside it -- both point predictions were
# falsified, in opposite directions, which is why the axis disagreement is
# reported as a finding rather than resolved by picking one.
H2_SPURIOUS_JOINT_STEPS = -0.0142
H2_SPURIOUS_JOINT_CHARS = -0.1917

# UNITS CAVEAT on the addition above. The two components do not share a
# denominator: the miss rate is over mathematical-layer explicit TARGETS,
# the spurious rate is over RESOLVED premises. Adding them treats both as
# premise fractions of the extracted set, which is an approximation, not an
# identity. It is the right order of magnitude and the right sign; it is not
# exact, and E3's per-metric simulation must apply the two rates separately
# rather than deleting/inserting at a single combined rate.

# The support criterion is H2_SUPPORT_CRITERION = "ci_above_band_top": the
# observed gap's 95% CI must lie entirely above band_top(D_m). There is no
# multiplier any more, so there is no "2.0 x combined" threshold to quote.

# Superseded. The 2026-08-13 log recorded +0.039 from a binary automation
# split with jixia strata and a length-stratified mix. Re-running that design
# against the census mix gives +0.061; correcting the strata instrument gives
# +0.109; the class refinement gives +0.129. See
# results/instrument_gap_decomposition.csv. Kept so the paper can state that
# the first estimate understated the confound by roughly 3x.
INSTRUMENT_GAP_BINARY = 0.039

RANDOM_SEED = 20260812
