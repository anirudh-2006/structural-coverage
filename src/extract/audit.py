"""Source-visible premise extraction and its audit.

THE HIGHEST-RISK COMPONENT. The Aug 21 gate lives here.

Framing (CLAUDE.md §4): source-visible extraction is not an approximation of
the compiler graph. It is the correct instrument for the EXPLICIT subgraph.
The audit measures how faithfully it recovers explicit edges — not all edges.
Reporting it against the full graph would understate retention by design.

Two things this module must get right, both of which are easy to get wrong
in a direction that flatters the result:

1. **The denominator is the MATHEMATICAL layer**, with all-explicit and
   infrastructure reported alongside (notes/decisions.md 2026-08-13 §2, and
   independently required by CLAUDE.md §4 rule 1). Infrastructure targets
   like `Eq.mpr` and `of_eq_true` are typed by nobody, so including them in
   the gate denominator measures Lean's elaborator, not our parser.

2. **The matcher must be comparable to the one that set the ceiling.**
   AUDIT_EFFICIENCY_THRESHOLD is retention / CEILING_MATHEMATICAL, and
   CEILING_MATHEMATICAL = 0.8193 is the LOOSE ceiling — it credits a target
   whose last component appears unqualified, because `p.primeCompl` really
   is how mathlib cites `Ideal.primeCompl`. Dividing a strict retention by a
   loose ceiling would be an apples-to-oranges ratio that fails by
   construction. So the gate uses the loose matcher and `retention_strict`
   is reported next to it as the conservative bound. See AuditResult.

The difference between this module and extract.ceiling is the search scope,
and that difference IS the instrument: the ceiling matches against the whole
FILE (an upper bound nothing can beat), this matches against the located
DECLARATION BLOCK. Efficiency is the ratio between them.

**Scope is the whole declaration — statement and proof — not the proof body.**
`is_explicit` edges come from the elaborated term of the entire declaration,
so its type contributes premises: in
`theorem foo (h : Nat.Prime p) : ...`, `Nat.Prime` is an explicit target.
Scoping extraction to everything after `:=` would drop those while leaving
them in the denominator, which is an under-scoped instrument rather than a
strict one. `decl_source.proof_body` exists for the A2 tactic calibration,
where the statement genuinely must be excluded; it is the wrong tool here.
Measured cost of the mistake on the audit sample: retention 0.574 -> 0.623.

**A per-declaration extractor cannot reach the whole-file ceiling**, and the
gate as frozen does not account for this. See `reachable_bound`: 9.7% of
mathematical explicit targets appear somewhere in the file but nowhere in
the declaration that depends on them. That fraction is unreachable for any
per-declaration instrument, so efficiency against CEILING_MATHEMATICAL is
capped near 0.88 — below the frozen 0.95 threshold. Reported, not silently
worked around; the response is a §6 judgement call.

Nothing here compiles Lean.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from src import config
from src.extract import ceiling, decl_source
from src.extract import source as src_mod
from src.graph import load

# --- tokenisation --------------------------------------------------------
# Lean identifiers: letters, digits, _, ', ! and ?, composed with dots. A
# leading dot is excluded here because `.mp` in `h.mp` is projection notation
# on a local hypothesis, not a reference to a root-level `mp`.
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_'!?]*(?:\.[A-Za-z0-9_'!?]+)*")

# Line comments, block comments (Lean nests them, hence the manual scan
# below rather than a regex), and string literals. Comments matter more than
# they look: 74.7% of machine proof-body text is natural-language comment
# (notes/decisions.md, A2 robustness), and comments are full of words like
# `bound` and `simp` that would otherwise resolve as premises.
_LINE_COMMENT = re.compile(r"--[^\n]*")
_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')

# Tactic and syntax keywords that are not premises. Kept deliberately short:
# anything not in this list still has to RESOLVE against the declaration set
# to count, so the list is a speed and precision aid, not the safety net.
# Over-long keyword lists are how a source extractor silently starts
# excluding real premises that share a name with a tactic.
_KEYWORDS = frozenset({
    "by", "at", "with", "fun", "let", "have", "show", "from", "this",
    "if", "then", "else", "do", "match", "deriving", "where", "in",
    "exact", "apply", "refine", "intro", "intros", "rintro", "obtain",
    "rcases", "cases", "rw", "rwa", "simp", "simpa", "simp_all", "norm_num",
    "ring", "ring_nf", "field_simp", "linarith", "nlinarith", "polyrith",
    "positivity", "omega", "decide", "aesop", "tauto", "bound", "constructor",
    "induction", "use", "exists", "refl", "rfl", "trivial", "sorry",
    "unfold", "subst", "specialize", "convert", "congr", "ext", "funext",
    "push_cast", "norm_cast", "gcongr", "calc", "conv", "set", "generalize",
    "left", "right", "exfalso", "contrapose", "by_cases", "by_contra",
    "assumption", "all_goals", "any_goals", "first", "try", "repeat",
    "nlinarith!", "linarith!", "and", "or", "not", "iff", "true", "false",
})


_TACTIC_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_.'])("
    + "|".join(sorted(config.COUNTABLE_TACTICS, key=len, reverse=True))
    + r")(?![A-Za-z0-9_'])"
)


def tactic_steps(proof_body: str) -> int:
    """Tactic invocations in a proof body: a WRAP-INVARIANT length measure.

    Lives here because both corpora must be counted with the same matcher and
    the same noise stripping, and `strip_noise` is here. Character length is
    NOT comparable across the corpora — mathlib source is hand-wrapped near
    100 columns and carries docstrings, a Goedel `full_proof` is generated —
    and the 2026-08-16 overlap check showed the difference is decisive: the
    two corpora overlap 0.215 on characters and 0.856 on tactic steps.
    """
    return len(_TACTIC_TOKEN.findall(strip_noise(proof_body)))


def strip_noise(text: str) -> str:
    """Remove comments and string literals, preserving offsets loosely.

    Block comments nest in Lean (`/- /- -/ -/`), so they are scanned rather
    than matched. Replacing with spaces rather than deleting keeps adjacent
    identifiers from being fused into one token.
    """
    out: list[str] = []
    i, depth, n = 0, 0, len(text)
    while i < n:
        if text.startswith("/-", i):
            depth += 1
            out.append("  ")
            i += 2
        elif text.startswith("-/", i) and depth:
            depth -= 1
            out.append("  ")
            i += 2
        elif depth:
            out.append(" " if text[i] != "\n" else "\n")
            i += 1
        else:
            out.append(text[i])
            i += 1
    cleaned = "".join(out)
    cleaned = _LINE_COMMENT.sub(lambda m: " " * len(m.group()), cleaned)
    cleaned = _STRING.sub(lambda m: " " * len(m.group()), cleaned)
    return cleaned


def identifier_tokens(proof_source: str) -> list[str]:
    """Every identifier-shaped token in the proof body, comments removed."""
    return _IDENT.findall(strip_noise(proof_source))


# --- resolution ----------------------------------------------------------


@dataclass(frozen=True)
class Extraction:
    """What the extractor found, split by how confident the resolution is.

    `resolved` is the premise set proper: tokens that name a declaration
    unambiguously. `suffix_tokens` is the dot-notation residue — bare last
    components like `mp`, `symm`, `le_refl` that cannot be resolved to one
    declaration without knowing the type of the local they are projected
    from, which needs elaboration. They are kept separate rather than
    resolved greedily, because greedy resolution of `.mp` would add every
    declaration in mathlib ending in `.mp` to the premise set and destroy
    precision.
    """

    resolved: frozenset[str]
    suffix_tokens: frozenset[str]
    # Subset of `resolved` that was NOT written as a fully-qualified name —
    # it completed under a namespace or `open` prefix (resolution step 2).
    # Diagnostic only: nothing in the audit reads it, so retention cannot
    # move. It exists because the two resolution steps carry different
    # false-positive risk (prefix completion ignores the section scoping of
    # `open`; exact matching has nothing to get wrong), and because a
    # standalone machine proof has almost no prefixes available — which makes
    # the mechanism mix the thing to compare across corpora.
    via_prefix: frozenset[str] = frozenset()


def _namespace_prefixes(decl_name: str, file_text: str | None) -> list[str]:
    """Candidate namespace prefixes a bare token might be written under.

    Two sources, both approximations:

      - the declaration's own name. `Ideal.Quotient.mk` is written inside
        `namespace Ideal.Quotient`, so `mk` in a neighbouring proof means
        `Ideal.Quotient.mk`. Every proper prefix is a candidate.
      - `open X` lines anywhere in the file. Lean scopes `open` to sections,
        and this ignores that, so it is over-permissive: it can resolve a
        token under a namespace that is not actually open at that point.
        The cost is precision (a spurious premise), never recall, and
        spurious is reported rather than gated.
    """
    parts = decl_name.split(".")
    prefixes = [".".join(parts[:i]) for i in range(len(parts) - 1, 0, -1)]
    if file_text:
        for m in re.finditer(r"^open\s+([^\n]+)", file_text, re.MULTILINE):
            clause = m.group(1).split("--")[0]
            if " in" in f" {clause} ":
                clause = clause.split(" in")[0]
            for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_'.]*", clause):
                if tok not in ("in", "scoped") and tok not in prefixes:
                    prefixes.append(tok)
    return prefixes


def extract(
    proof_source: str,
    known_declarations: frozenset[str] | set[str],
    decl_name: str = "",
    file_text: str | None = None,
) -> Extraction:
    """Resolve the proof body's identifier tokens against the graph's names.

    Resolution order per token, first hit wins:
      1. the token IS a fully-qualified declaration name;
      2. the token completes to one under a namespace prefix in scope;
      3. otherwise, if it is a bare single component, it is kept as a suffix
         token for the dot-notation credit described in Extraction.

    Note what this does NOT do: it never searches the declaration set by
    suffix. That would be the whole-file ceiling matcher applied to a proof
    body, and it would resolve `mp` to hundreds of declarations.
    """
    prefixes = _namespace_prefixes(decl_name, file_text) if decl_name else []
    resolved: set[str] = set()
    exact: set[str] = set()
    via_prefix: set[str] = set()
    suffixes: set[str] = set()

    for token in identifier_tokens(proof_source):
        if token in _KEYWORDS:
            continue
        if token in known_declarations:
            resolved.add(token)
            exact.add(token)
            continue
        hit = next(
            (f"{p}.{token}" for p in prefixes if f"{p}.{token}" in known_declarations),
            None,
        )
        if hit is not None:
            resolved.add(hit)
            via_prefix.add(hit)
            continue
        # Unresolved. The last component is what a dot-notation citation
        # would have written, so keep it for the loose match.
        suffixes.add(token.rsplit(".", 1)[-1])

    # A name can arrive by both routes within one declaration (written out
    # once, abbreviated once). It is credited to the exact route, which is
    # the conservative direction for the precision diagnostic: it keeps the
    # prefix-only set to names that ONLY ever arrived by completion.
    return Extraction(
        frozenset(resolved), frozenset(suffixes), frozenset(via_prefix - exact)
    )


def extract_premises(proof_source: str, known_declarations: set[str]) -> set[str]:
    """Parse premise references from Lean proof source text.

    The unambiguously-resolved premise set. Callers needing the dot-notation
    residue (the audit does, to stay comparable with the loose ceiling)
    should call `extract` instead.
    """
    return set(extract(proof_source, known_declarations).resolved)


# --- the audit -----------------------------------------------------------


@dataclass
class AuditResult:
    """Retention of explicit edges, per layer.

    Counts are over EDGES, not declarations. The scaffold version of this
    class divided by declaration count, which is not a retention rate.
    """

    sample_size: int = 0
    recovered: int = 0
    missed: int = 0
    spurious: int = 0

    # (recovered, total) per layer under each matcher.
    loose: dict[str, tuple[int, int]] = field(default_factory=dict)
    strict: dict[str, tuple[int, int]] = field(default_factory=dict)

    located: int = 0
    unlocated: int = 0
    unreachable_targets: int = 0
    paired_ceiling: float = 0.0
    reachable_bound: float = 0.0
    top_missed: list[tuple[str, int]] = field(default_factory=list)

    @staticmethod
    def _rate(pair: tuple[int, int]) -> float:
        matched, total = pair
        return matched / total if total else 0.0

    @property
    def retention(self) -> float:
        """Loose retention on the mathematical layer. THE gate number."""
        return self._rate(self.loose.get("mathematical", (0, 0)))

    @property
    def retention_strict(self) -> float:
        return self._rate(self.strict.get("mathematical", (0, 0)))

    @property
    def efficiency(self) -> float:
        """Retention against the frozen ceiling. The gate is a ratio."""
        return self.retention / config.CEILING_MATHEMATICAL

    @property
    def efficiency_paired(self) -> float:
        """Against the ceiling recomputed on THIS sample, as a robustness
        check. Not the gate — the gate is fixed against the frozen constant
        so it cannot drift with the sample."""
        return self.retention / self.paired_ceiling if self.paired_ceiling else 0.0

    @property
    def efficiency_reachable(self) -> float:
        """Against the bound a per-declaration extractor can actually reach:
        the ceiling's own loose matcher, scoped to the declaration block
        instead of the whole file. This is the number that says whether the
        PARSER is good. `efficiency` says whether the parser can clear a
        threshold set against a scope it does not operate at."""
        return self.retention / self.reachable_bound if self.reachable_bound else 0.0

    @property
    def retention_worst_case(self) -> float:
        """Every declaration whose body could not be located counted as a
        total loss. Locate failures are an instrument limitation on a
        different axis (auto-named instances have no textual declaration
        site), so the headline excludes them — but excluding them silently
        would be flattering, so the bound is reported."""
        rec, total = self.loose.get("mathematical", (0, 0))
        if not total or not self.located:
            return 0.0
        implied = total / self.located * (self.located + self.unlocated)
        return rec / implied

    @property
    def passes_gate(self) -> bool:
        return self.efficiency >= config.AUDIT_EFFICIENCY_THRESHOLD

    def report(self) -> str:
        header = (
            f"extraction audit  n={self.sample_size} declarations "
            f"({self.located} located, {self.unlocated} not)"
        )
        lines = [header, "", f"{'layer':<26}{'loose':>18}{'strict':>18}"]
        for layer in ("mathematical", "infrastructure", "all_explicit"):
            lo = self.loose.get(layer, (0, 0))
            st = self.strict.get(layer, (0, 0))
            lines.append(
                f"{layer:<26}"
                f"{self._rate(lo):>7.3f} ({lo[0]:>4}/{lo[1]:<5})"
                f"{self._rate(st):>9.3f} ({st[0]:>4}/{st[1]:<5})"
            )
        unreachable = max(0.0, self.paired_ceiling - self.reachable_bound)
        gate = [
            f"GATE  retention (loose, mathematical) = {self.retention:.4f}",
            (
                f"      ceiling (frozen)                = "
                f"{config.CEILING_MATHEMATICAL:.4f}"
            ),
            (
                f"      efficiency                      = {self.efficiency:.4f}"
                f"   threshold {config.AUDIT_EFFICIENCY_THRESHOLD}"
            ),
            f"      -> {'PASS' if self.passes_gate else 'FAIL'}",
            "",
            (
                f"      implied absolute floor          = "
                f"{config.AUDIT_RETENTION_THRESHOLD:.4f}"
            ),
            (
                f"      ceiling paired on this sample   = "
                f"{self.paired_ceiling:.4f}"
                f"   -> efficiency {self.efficiency_paired:.4f}"
            ),
            (
                f"      REACHABLE bound (declaration scope) = "
                f"{self.reachable_bound:.4f}"
            ),
            (
                f"      efficiency against reachable    = "
                f"{self.efficiency_reachable:.4f}"
            ),
            (
                f"      structurally unreachable per-decl = {unreachable:.4f}"
                f"  (in the file, not in the declaration)"
            ),
            (
                f"      retention if unlocated count as total loss = "
                f"{self.retention_worst_case:.4f}"
            ),
            f"      retention strict (conservative) = {self.retention_strict:.4f}",
            "",
            f"spurious (resolved, not an explicit target): {self.spurious}",
            (
                f"targets not in the declaration set:          "
                f"{self.unreachable_targets}"
            ),
            "",
            "most-missed targets (loose, mathematical):",
        ]
        lines += ["", *gate]
        lines += [f"  {n:<44}{c:>5}" for n, c in self.top_missed]
        return "\n".join(lines)


def run_audit(sample_size: int | None = None) -> AuditResult:
    """Compare extracted premises against the published explicit subgraph.

    The returned retention rate goes in the paper verbatim.

    Sampling reuses ceiling.sample_declarations with the same seed, so the
    audit sample is the ceiling sample extended — the efficiency ratio is
    paired rather than comparing two independent draws.
    """
    n = sample_size or config.AUDIT_SAMPLE_SIZE
    g = load.load_explicit_graph()
    _, mathematical = load.split_hub_layers(g)
    known = frozenset(load.declaration_names(g))

    result = AuditResult()
    counts = {
        k: {"loose": [0, 0], "strict": [0, 0]}
        for k in ("mathematical", "infrastructure", "all_explicit")
    }
    missed: Counter[str] = Counter()
    ceil_hit = ceil_tot = reach_hit = 0

    # One file_blocks index per file rather than a rescan per declaration.
    block_cache: dict[str, dict[str, str]] = {}

    for decl in ceiling.sample_declarations(g, n, seed=config.RANDOM_SEED):
        module = g.nodes[decl]["file_module"]
        text = src_mod.read_module_source(module)
        if text is None:
            result.unlocated += 1
            continue
        if module not in block_cache:
            block_cache[module] = decl_source.file_blocks(text)
        block = decl_source.block_from_file_index(decl, block_cache[module])
        if block is None:
            result.unlocated += 1
            continue

        result.located += 1
        result.sample_size += 1
        # Whole declaration, not proof_body(block) — see the module docstring.
        found = extract(block, known, decl_name=decl, file_text=text)

        targets = [t for t in g.successors(decl) if t in known]
        result.unreachable_targets += g.out_degree(decl) - len(targets)

        for target in targets:
            layer = "mathematical" if target in mathematical else "infrastructure"
            hit_strict = target in found.resolved
            # Loose credit mirrors the ceiling's loose matcher: the target's
            # last component written unqualified, i.e. dot notation.
            hit_loose = hit_strict or (
                ceiling.last_component(target) in found.suffix_tokens
            )
            for key in (layer, "all_explicit"):
                counts[key]["loose"][1] += 1
                counts[key]["strict"][1] += 1
                counts[key]["loose"][0] += hit_loose
                counts[key]["strict"][0] += hit_strict
            if layer == "mathematical":
                ceil_tot += 1
                # Same loose matcher at two scopes: the whole file (what set
                # the frozen ceiling) and the declaration block (what any
                # per-declaration extractor can actually see).
                ceil_hit += ceiling.name_or_suffix_occurs(target, text)
                reach_hit += ceiling.name_or_suffix_occurs(target, block)
                if not hit_loose:
                    missed[target] += 1

        result.spurious += len(found.resolved - set(targets))

    for layer, c in counts.items():
        result.loose[layer] = (c["loose"][0], c["loose"][1])
        result.strict[layer] = (c["strict"][0], c["strict"][1])
    result.recovered = result.loose["mathematical"][0]
    result.missed = result.loose["mathematical"][1] - result.recovered
    result.paired_ceiling = ceil_hit / ceil_tot if ceil_tot else 0.0
    result.reachable_bound = reach_hit / ceil_tot if ceil_tot else 0.0
    result.top_missed = missed.most_common(15)
    return result


def write_results(result: AuditResult) -> None:
    """Commit the gate numbers. Small CSV, regenerable from seed."""
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    out = config.RESULTS / "extraction_audit.csv"
    rows = ["layer,matcher,recovered,total,rate"]
    for layer in ("mathematical", "infrastructure", "all_explicit"):
        for matcher, table in (("loose", result.loose), ("strict", result.strict)):
            r, t = table[layer]
            rows.append(f"{layer},{matcher},{r},{t},{r / t if t else 0:.4f}")
    sampled = result.located + result.unlocated
    rows += [
        (
            f"gate,efficiency,{result.retention:.4f},"
            f"{config.CEILING_MATHEMATICAL},{result.efficiency:.4f}"
        ),
        (
            f"gate,efficiency_paired,{result.retention:.4f},"
            f"{result.paired_ceiling:.4f},{result.efficiency_paired:.4f}"
        ),
        (
            f"gate,worst_case,{result.recovered},{sampled},"
            f"{result.retention_worst_case:.4f}"
        ),
        (
            f"gate,efficiency_reachable,{result.retention:.4f},"
            f"{result.reachable_bound:.4f},{result.efficiency_reachable:.4f}"
        ),
    ]
    out.write_text("\n".join(rows) + "\n")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    import sys

    size = int(sys.argv[1]) if len(sys.argv) > 1 else None
    res = run_audit(size)
    print(res.report())
    write_results(res)
