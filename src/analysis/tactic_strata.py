"""Amendments 1 and 2 to the automation confound control (2026-08-13).

Amendment 1 — stratify on TACTIC CLASS, not a binary automation flag.
The binary split leaves the confound inside the automation stratum. Machine
automation is nlinarith-dominated (65.7% of Goedel proofs); human automation
is not. If the classes have different miss rates, "both corpora use
automation" is not a control, and the corrected figure must come from direct
standardization over the class mix rather than a two-cell adjustment.

Amendment 2 — calibrate the two instruments against each other.
The human automation rate (0.495) came from the publishers' jixia tactic
lists; the machine rate (0.960) from string matching. The 0.464 gap was
asserted to be mostly real. This measures it: run the string matcher over
located human proof bodies and compare, per tactic, against jixia on the same
declarations.

Sampling design. Rates and mixes are estimated from different populations on
purpose:

  * per-class MISS RATES come from a class-targeted sample, because `arith`
    and `decide` are rare enough in mathlib that a representative draw yields
    single digits — and `arith` is the stratum carrying 76% of the machine
    corpus. A within-stratum rate is unaffected by oversampling that stratum.
  * the human class MIX is a census over every eligible mathlib tactic proof
    whose body can be located. Sampling it would add noise for nothing.

One instrument throughout. The calibration below showed jixia does not
record tactics after `<;>`, inside `induction … with` branches, or in nested
`(by simp …)` terms, so a jixia-cut human mix compared against a
matcher-cut machine mix charges the instrument difference to the corpus.
Strata and mixes are therefore both cut with the string matcher, and jixia
appears only as a sensitivity row.

TWO SEPARATE INSTRUMENT AXES LIVE IN THIS MODULE. Do not conflate them:

  * how a proof's STRATUM is cut — jixia tactic lists vs the string matcher.
    That is `tactics_of` (MATCHER_TACTICS / JIXIA_TACTICS), amendment 2.
  * how a premise is counted RECOVERED — the whole-file ceiling matcher vs
    the real declaration-scope extractor. That is `hits_of` (CEILING_HITS /
    EXTRACTOR_HITS), added 2026-08-16.

The second axis was originally not an axis at all: the 2026-08-13 run
counted recovery with `ceiling.name_or_suffix_occurs` against the whole
FILE, because no extractor existed yet. It does now, and E3 will run on it,
so `INSTRUMENT_MISS_RATE_BY_CLASS` has to be cut with the instrument E3
actually uses. Aggregate mathematical-layer miss is 0.2085 under the ceiling
matcher and 0.3876 under the extractor (audit, n=187) — a 1.86x move, so the
rates are not transferable between the two. EXTRACTOR_HITS is the default.

Still instrument validation, not an H2 metric. CLAUDE.md §6 freezes metric
definitions; none exist yet.
"""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache

import networkx as nx
import pandas as pd

from src import config
from src.analysis.automation_confound import (
    GOEDEL_PARQUET,
    _proof_body,
    automation_tactics_in_text,
)
from src.extract import audit, ceiling, decl_source
from src.extract import source as src_mod
from src.graph import load

ALL_CLASSES = (*config.TACTIC_CLASS_PRECEDENCE, config.TACTIC_CLASS_NONE)

# Which instrument defines a record's stratum. The matcher is primary: it is
# the only instrument available on the machine side, so cutting the human
# strata any other way makes the standardization compare two different
# measurements. JIXIA_TACTICS is the sensitivity alternative.
def MATCHER_TACTICS(r: DeclRecord) -> Iterable[str]:
    return r.matched_tactics


def JIXIA_TACTICS(r: DeclRecord) -> Iterable[str]:
    return r.jixia_tactics


# Which instrument decides that a premise was RECOVERED. The extractor is
# primary from 2026-08-16: it is what E3 runs on, so per-class miss rates cut
# any other way would parameterize the H2 reference line with a blind spot the
# analysis never has. CEILING_HITS reproduces the superseded 2026-08-13 rates
# and is retained for the decomposition row only.
def EXTRACTOR_HITS(r: DeclRecord) -> int:
    return r.hits_extractor


def CEILING_HITS(r: DeclRecord) -> int:
    return r.hits


def REACHABLE_HITS(r: DeclRecord) -> int:
    return r.hits_reachable

# Cap per class in the rate sample. arith (252) and decide (139) fall under
# it and are therefore censused; simp / other / none are capped for runtime.
CLASS_SAMPLE_CAP = 400


# --- class assignment ----------------------------------------------------

def classes_used(tactics: Iterable[str]) -> set[str]:
    """Every class the proof touches. Overlapping — for MARGINAL rates."""
    seen = set(tactics)
    return {
        cls for cls, members in config.TACTIC_CLASSES.items() if seen & members
    }


def assign_class(
    tactics: Iterable[str],
    precedence: Sequence[str] = config.TACTIC_CLASS_PRECEDENCE,
) -> str:
    """The proof's single stratum. A PARTITION — for standardization.

    Precedence is a researcher degree of freedom, so it is a parameter and
    `precedence_sensitivity` sweeps every ordering.
    """
    used = classes_used(tactics)
    for cls in precedence:
        if cls in used:
            return cls
    return config.TACTIC_CLASS_NONE


# --- population ----------------------------------------------------------

@lru_cache(maxsize=1)
def _explicit_graph() -> nx.DiGraph:
    """One shared load. 2.2M edges is expensive to build twice."""
    return load.load_explicit_graph()


def eligible_declarations(g: nx.DiGraph) -> list[str]:
    """Same predicate ceiling.sample_declarations draws from, unstratified."""
    return [
        name
        for name, a in g.nodes(data=True)
        if a["kind"] == "theorem"
        and a["file_module"].startswith(config.MATHLIB_MODULE_PREFIX)
        and a["is_tactic_proof"]
        and g.out_degree(name) > 0
    ]


# --- one pass over a set of human declarations ---------------------------

@dataclass
class DeclRecord:
    """One sampled human declaration, seen through both instruments."""

    name: str
    jixia_tactics: list[str]
    located: bool
    matched_tactics: set[str]   # string matcher on the located body
    block_chars: int            # declaration block length, for length control
    tactic_steps: int           # wrap-invariant length; see audit.tactic_steps
    targets: int                # mathematical-layer explicit dependencies
    hits: int                   # of those, recoverable by whole-file matching
    # Of those, recovered by the REAL extractor at declaration scope, under
    # the same loose credit the audit uses (resolved, or the target's last
    # component present as a dot-notation suffix token).
    hits_extractor: int = 0
    # The SAME loose matcher as `hits`, scoped to the declaration block. Sits
    # between the two and splits their difference into its two causes: scope
    # (file -> declaration) and resolution (substring -> identifier). Both are
    # properties E3 lives with, so this is diagnostic, not a candidate basis.
    hits_reachable: int = 0
    # Precision side, for the spurious-symmetry check. Counted over ALL
    # explicit targets, both layers, exactly as extract.audit does.
    resolved: int = 0
    spurious: int = 0
    resolved_exact: int = 0     # token WAS a fully-qualified declaration name
    spurious_exact: int = 0
    resolved_prefix: int = 0    # token completed under a namespace/open prefix
    spurious_prefix: int = 0

    @property
    def miss(self) -> int:
        return self.targets - self.hits

    @property
    def miss_extractor(self) -> int:
        return self.targets - self.hits_extractor


def _record(
    decl: str,
    g: nx.DiGraph,
    mathematical: set[str],
    usage: dict[str, list[str]],
    matcher_index: dict[str, frozenset[str]],
    known: frozenset[str],
    block_index: dict[str, str],
) -> DeclRecord | None:
    text = src_mod.read_module_source(g.nodes[decl]["file_module"])
    if text is None:
        return None

    # The real extractor, identical to extract.audit: whole declaration block
    # (statement included — `is_explicit` edges come from the elaborated term
    # of the whole declaration), resolved against the graph's declaration
    # names with the file's `open` lines in scope.
    block = block_index.get(decl)
    found = (
        audit.extract(block, known, decl_name=decl, file_text=text)
        if block is not None
        else None
    )
    prefix = set(found.via_prefix) if found else set()
    exact = (set(found.resolved) - prefix) if found else set()

    targets = hits = hits_extractor = hits_reachable = 0
    for target in g.successors(decl):
        if target not in mathematical:
            continue
        targets += 1
        hits += ceiling.name_or_suffix_occurs(target, text)
        if found is not None:
            hits_extractor += target in found.resolved or (
                ceiling.last_component(target) in found.suffix_tokens
            )
            hits_reachable += ceiling.name_or_suffix_occurs(target, block)
    if targets == 0:
        return None

    all_targets = {t for t in g.successors(decl) if t in known}
    resolved = found.resolved if found else frozenset()
    matched = matcher_index.get(decl)
    return DeclRecord(
        name=decl,
        jixia_tactics=usage.get(decl, []),
        located=matched is not None,
        matched_tactics=set(matched) if matched is not None else set(),
        block_chars=len(block) if block is not None else 0,
        tactic_steps=(
            audit.tactic_steps(decl_source.proof_body(block))
            if block is not None else 0
        ),
        targets=targets,
        hits=hits,
        hits_extractor=hits_extractor,
        hits_reachable=hits_reachable,
        resolved=len(resolved),
        spurious=len(resolved - all_targets),
        resolved_exact=len(exact),
        spurious_exact=len(exact - all_targets),
        resolved_prefix=len(prefix),
        spurious_prefix=len(prefix - all_targets),
    )




def collect_by_class(
    cap: int = CLASS_SAMPLE_CAP,
    seed: int = config.RANDOM_SEED,
) -> tuple[list[DeclRecord], dict[str, int]]:
    """Class-targeted sample: up to `cap` declarations per marginal class.

    Bucketing uses the MATCHER classes, because the mixes this feeds are
    matcher censuses on both sides — strata and mix have to be cut by the
    same instrument or the standardization is incoherent.

    Sampling is on MARGINAL membership, so the pooled set populates every
    partition stratum under any precedence ordering; the sweep in
    `precedence_sensitivity` would otherwise be re-sampling as it goes.

    Returns the records and the population size of each marginal class, so
    census-vs-sample can be reported per class.
    """
    g = _explicit_graph()
    _, mathematical = load.split_hub_layers(g)
    usage = load.load_tactic_usage()
    matcher_index, block_index, _ = _human_census()
    known = frozenset(load.declaration_names(g))

    buckets: dict[str, list[str]] = {c: [] for c in ALL_CLASSES}
    for name, tactics in matcher_index.items():
        for cls in classes_used(tactics) or {config.TACTIC_CLASS_NONE}:
            buckets[cls].append(name)

    population = {c: len(v) for c, v in buckets.items()}
    rng = random.Random(seed)
    picked: set[str] = set()
    for cls in ALL_CLASSES:
        names = sorted(buckets[cls])
        picked.update(rng.sample(names, min(cap, len(names))))

    records = []
    for decl in sorted(picked):
        rec = _record(decl, g, mathematical, usage, matcher_index, known, block_index)
        if rec is not None:
            records.append(rec)
    return records, population


# --- amendment 1: do the per-class rates diverge? ------------------------

def _rate(
    records: Iterable[DeclRecord], hits_of=EXTRACTOR_HITS
) -> tuple[int, int, int, float]:
    recs = list(records)
    targets = sum(r.targets for r in recs)
    miss = sum(r.targets - hits_of(r) for r in recs)
    return len(recs), targets, miss, (miss / targets if targets else float("nan"))


_INSTRUMENT_NAMES = {
    id(EXTRACTOR_HITS): "extractor",
    id(CEILING_HITS): "ceiling_matcher",
    id(REACHABLE_HITS): "reachable_bound",
}


def _instrument_name(hits_of) -> str:
    return _INSTRUMENT_NAMES.get(id(hits_of), "unknown")


def marginal_miss_rates(
    records: Sequence[DeclRecord],
    population: dict[str, int] | None = None,
    tactics_of=MATCHER_TACTICS,
    hits_of=EXTRACTOR_HITS,
) -> pd.DataFrame:
    """Miss rate among proofs TOUCHING each class. Classes overlap here.

    The direct answer to "do per-tactic rates diverge" — independent of any
    precedence ordering.
    """
    rows = []
    for cls in ALL_CLASSES:
        if cls == config.TACTIC_CLASS_NONE:
            sel = [r for r in records if not classes_used(tactics_of(r))]
        else:
            sel = [r for r in records if cls in classes_used(tactics_of(r))]
        decls, targets, miss, rate = _rate(sel, hits_of)
        rows.append({
            "class": cls, "basis": "marginal",
            "instrument": _instrument_name(hits_of), "declarations": decls,
            "population": (population or {}).get(cls, -1),
            "targets": targets, "missed": miss, "miss_rate": rate,
        })
    return pd.DataFrame(rows)


def partition_miss_rates(
    records: Sequence[DeclRecord],
    precedence: Sequence[str] = config.TACTIC_CLASS_PRECEDENCE,
    tactics_of=MATCHER_TACTICS,
    hits_of=EXTRACTOR_HITS,
) -> pd.DataFrame:
    """Miss rate per stratum of the PARTITION. Feeds standardization."""
    rows = []
    for cls in ALL_CLASSES:
        sel = [r for r in records if assign_class(tactics_of(r), precedence) == cls]
        decls, targets, miss, rate = _rate(sel, hits_of)
        rows.append({
            "class": cls, "basis": "partition",
            "instrument": _instrument_name(hits_of), "declarations": decls,
            "population": -1, "targets": targets, "missed": miss,
            "miss_rate": rate,
        })
    return pd.DataFrame(rows)


# --- class mixes ---------------------------------------------------------

@lru_cache(maxsize=1)
def _human_tactic_sets() -> tuple[frozenset[str], ...]:
    """Jixia tactic set for every eligible mathlib tactic proof.

    Cached: the 24-way precedence sweep would otherwise reload the graph
    and the 45MB ndjson once per ordering.
    """
    g = _explicit_graph()
    usage = load.load_tactic_usage()
    return tuple(
        frozenset(usage.get(name, [])) for name in eligible_declarations(g)
    )


@lru_cache(maxsize=1)
def _human_census() -> tuple[dict[str, frozenset[str]], dict[str, str], int]:
    """One pass over every eligible mathlib tactic proof: tactics AND block.

    The tactic index exists because the jixia census and the machine matcher
    census are NOT the same instrument, and the calibration showed the
    difference is material (jixia does not record tactics after `<;>`, inside
    `induction … with` branches, or in nested `(by simp …)` terms).
    Standardizing a jixia-based human mix against a matcher-based machine mix
    would charge the instrument difference to the corpus difference.

    The block index exists because the real extractor operates at declaration
    scope and needs the block text. It is the SAME located block the tactic
    matcher is run on, so the stratum and the miss rate for a declaration can
    never come from two different pieces of text.

    Returns ({name: matcher tactics}, {name: declaration block}, eligible
    seen). Unlocated declarations are EXCLUDED from both, never silently
    counted as `none`.
    """
    g = _explicit_graph()
    by_module: dict[str, list[str]] = {}
    for name in eligible_declarations(g):
        by_module.setdefault(g.nodes[name]["file_module"], []).append(name)

    index: dict[str, frozenset[str]] = {}
    block_index: dict[str, str] = {}
    seen = 0
    for module, names in by_module.items():
        text = src_mod.read_module_source(module)
        if text is None:
            seen += len(names)
            continue
        blocks = decl_source.file_blocks(text)
        for name in names:
            seen += 1
            block = decl_source.block_from_file_index(name, blocks)
            if block is not None:
                block_index[name] = block
                index[name] = frozenset(
                    automation_tactics_in_text(decl_source.proof_body(block))
                )
    return index, block_index, seen


def _human_matcher_index() -> tuple[dict[str, frozenset[str]], int]:
    """Back-compat view of `_human_census`: tactics and the eligible count."""
    index, _, seen = _human_census()
    return index, seen


@lru_cache(maxsize=1)
def _machine_tactic_sets() -> tuple[frozenset[str], ...]:
    """Matcher tactic set for every Goedel proof. Cached for the same reason."""
    df = pd.read_parquet(GOEDEL_PARQUET)
    found = df["full_proof"].map(_proof_body).map(automation_tactics_in_text)
    return tuple(frozenset(s) for s in found)


def _mix(
    tactic_sets: Sequence[frozenset[str]], precedence: Sequence[str]
) -> dict[str, float]:
    counts = {c: 0 for c in ALL_CLASSES}
    for ts in tactic_sets:
        counts[assign_class(ts, precedence)] += 1
    return {c: n / len(tactic_sets) for c, n in counts.items()}


def human_class_mix_census(
    precedence: Sequence[str] = config.TACTIC_CLASS_PRECEDENCE,
    instrument: str = "matcher",
) -> dict[str, float]:
    """Census over every eligible mathlib tactic proof.

    `instrument="matcher"` is the DEFAULT and the one used for the reference
    line: it is the only choice under which the human and machine mixes are
    measured the same way. `instrument="jixia"` is retained for the
    sensitivity row, and is what the 2026-08-13 binary figure used.
    """
    if instrument == "jixia":
        return _mix(_human_tactic_sets(), precedence)
    index, _ = _human_matcher_index()
    return _mix(tuple(index.values()), precedence)


def machine_class_mix(
    precedence: Sequence[str] = config.TACTIC_CLASS_PRECEDENCE,
) -> dict[str, float]:
    """Share of Goedel proofs in each stratum, under the string matcher."""
    return _mix(_machine_tactic_sets(), precedence)


def human_class_mix_from_records(
    records: Sequence[DeclRecord],
    precedence: Sequence[str] = config.TACTIC_CLASS_PRECEDENCE,
    tactics_of=MATCHER_TACTICS,
) -> dict[str, float]:
    """Mix within a record set. Only valid on a REPRESENTATIVE draw — the
    class-targeted sample is deliberately not one. Used for the
    same-instrument sensitivity check, where both sides must come from the
    matcher and no census is available."""
    counts = {c: 0 for c in ALL_CLASSES}
    for r in records:
        counts[assign_class(tactics_of(r), precedence)] += 1
    return {c: n / len(records) for c, n in counts.items()}


# --- standardization -----------------------------------------------------

def standardize(rates: dict[str, float], mix: dict[str, float]) -> float:
    """Direct standardization: Σ_c w_c · r_c.

    Renormalises over strata with a defined rate, so an empty stratum cannot
    silently contribute zero miss.
    """
    usable = {
        c: w for c, w in mix.items()
        if c in rates and not math.isnan(rates[c])
    }
    total = sum(usable.values())
    if not total:
        return float("nan")
    return sum(w * rates[c] for c, w in usable.items()) / total


def _rates_dict(frame: pd.DataFrame) -> dict[str, float]:
    return dict(zip(frame["class"], frame["miss_rate"]))


def standardized_gap(
    records: Sequence[DeclRecord],
    human_mix: dict[str, float],
    machine_mix: dict[str, float],
    precedence: Sequence[str] = config.TACTIC_CLASS_PRECEDENCE,
    tactics_of=MATCHER_TACTICS,
    hits_of=EXTRACTOR_HITS,
) -> tuple[float, float, float]:
    """(imputed human, imputed machine, gap) in premise-fraction units.

    Both sides use the HUMAN per-class miss rates — machine miss rates cannot
    be measured without elaborating machine proofs (scope check in
    notes/decisions.md). Only the class mix differs. That transfer assumption
    is load-bearing and is stated in the paper.
    """
    rates = _rates_dict(
        partition_miss_rates(records, precedence, tactics_of, hits_of)
    )
    h = standardize(rates, human_mix)
    m = standardize(rates, machine_mix)
    return h, m, m - h


def bootstrap_gap(
    records: Sequence[DeclRecord],
    human_mix: dict[str, float],
    machine_mix: dict[str, float],
    precedence: Sequence[str] = config.TACTIC_CLASS_PRECEDENCE,
    resamples: int = config.H2_BOOTSTRAP_RESAMPLES,
    seed: int = config.RANDOM_SEED,
    hits_of=EXTRACTOR_HITS,
) -> tuple[float, float]:
    """CI on the standardized gap, resampling DECLARATIONS within stratum.

    Edges inside a declaration are not independent — one automation call
    hides all of them at once — so an edge-level bootstrap would understate
    the interval badly. Resampling is stratified because the sample is.
    """
    strata: dict[str, list[DeclRecord]] = {c: [] for c in ALL_CLASSES}
    for r in records:
        strata[assign_class(r.matched_tactics, precedence)].append(r)

    rng = random.Random(seed)
    gaps = []
    for _ in range(resamples):
        draw: list[DeclRecord] = []
        for members in strata.values():
            if not members:
                continue
            draw += [members[rng.randrange(len(members))] for _ in members]
        _, _, gap = standardized_gap(
            draw, human_mix, machine_mix, precedence, hits_of=hits_of
        )
        if not math.isnan(gap):
            gaps.append(gap)
    gaps.sort()
    alpha = (1 - config.H2_BOOTSTRAP_CI) / 2
    return gaps[int(alpha * len(gaps))], gaps[min(len(gaps) - 1, int((1 - alpha) * len(gaps)))]


def binary_standardized_gap(
    records: Sequence[DeclRecord],
    human_mix: dict[str, float],
    machine_mix: dict[str, float],
    tactics_of=MATCHER_TACTICS,
    hits_of=EXTRACTOR_HITS,
) -> tuple[float, float, float]:
    """The same standardization under the OLD binary automation/none split.

    Isolates how much of the change from the 2026-08-13 figure is the class
    refinement and how much is the instrument fix: run this with the
    corrected strata and mixes, and whatever separates it from
    `standardized_gap` is attributable to the classes alone.
    """
    auto = [r for r in records if classes_used(tactics_of(r))]
    none = [r for r in records if not classes_used(tactics_of(r))]
    rates = {
        "automation": _rate(auto, hits_of)[3],
        config.TACTIC_CLASS_NONE: _rate(none, hits_of)[3],
    }

    def collapse(mix: dict[str, float]) -> dict[str, float]:
        none_w = mix[config.TACTIC_CLASS_NONE]
        return {"automation": 1.0 - none_w, config.TACTIC_CLASS_NONE: none_w}

    h = standardize(rates, collapse(human_mix))
    m = standardize(rates, collapse(machine_mix))
    return h, m, m - h


def decomposition(
    records: Sequence[DeclRecord],
    human_mix: dict[str, float],
    machine_mix: dict[str, float],
    jixia_mix: dict[str, float],
) -> pd.DataFrame:
    """Attribute the move from the 2026-08-13 figure to its causes.

    Four steps now, not three. The first three are the 2026-08-13 amendments
    and all run on the CEILING MATCHER, so they reproduce the superseded
    +0.039 -> +0.061 -> +0.109 -> +0.129 chain exactly. The fourth swaps the
    recovery instrument for the real extractor, which is what E3 runs on and
    therefore what the H2 reference line must be parameterized by.
    """
    _, _, binary_jixia = binary_standardized_gap(
        records, jixia_mix, machine_mix,
        tactics_of=JIXIA_TACTICS, hits_of=CEILING_HITS,
    )
    _, _, binary_matcher = binary_standardized_gap(
        records, human_mix, machine_mix, hits_of=CEILING_HITS
    )
    _, _, per_class = standardized_gap(
        records, human_mix, machine_mix, hits_of=CEILING_HITS
    )
    _, _, reachable = standardized_gap(
        records, human_mix, machine_mix, hits_of=REACHABLE_HITS
    )
    _, _, extractor = standardized_gap(
        records, human_mix, machine_mix, hits_of=EXTRACTOR_HITS
    )
    return pd.DataFrame([
        {"step": "binary split, jixia strata (2026-08-13 design)",
         "recovery_instrument": "ceiling_matcher",
         "gap": binary_jixia, "delta": float("nan")},
        {"step": "binary split, matcher strata + census mix",
         "recovery_instrument": "ceiling_matcher",
         "gap": binary_matcher, "delta": binary_matcher - binary_jixia},
        {"step": "per-class split, matcher strata + census mix",
         "recovery_instrument": "ceiling_matcher",
         "gap": per_class, "delta": per_class - binary_matcher},
        {"step": "  ... scope only: decl-scope substring matcher",
         "recovery_instrument": "reachable_bound",
         "gap": reachable, "delta": reachable - per_class},
        {"step": "per-class split, REAL EXTRACTOR recovery (2026-08-16)",
         "recovery_instrument": "extractor",
         "gap": extractor, "delta": extractor - reachable},
    ])


def precedence_sensitivity(
    records: Sequence[DeclRecord], hits_of=EXTRACTOR_HITS
) -> pd.DataFrame:
    """The standardized gap under every ordering of the four classes.

    If this range is wide the precedence rule is load-bearing, and it has to
    be reported rather than buried in config.
    """
    rows = []
    for order in itertools.permutations(config.TACTIC_CLASS_PRECEDENCE):
        h, m, gap = standardized_gap(
            records, human_class_mix_census(order), machine_class_mix(order), order,
            hits_of=hits_of,
        )
        rows.append({
            "precedence": ">".join(order), "instrument": _instrument_name(hits_of),
            "imputed_human": h, "imputed_machine": m, "gap": gap,
        })
    return pd.DataFrame(rows).sort_values("gap").reset_index(drop=True)


# --- amendment 2: instrument calibration ---------------------------------

def calibration(records: Sequence[DeclRecord]) -> pd.DataFrame:
    """String matcher vs jixia, per tactic, on the same human declarations.

    Restricted to declarations whose proof body could be located. The
    location rate is reported alongside because failures are not random —
    auto-named instances dominate them.
    """
    located = [r for r in records if r.located]
    rows = []
    for tactic in sorted(config.AUTOMATION_TACTICS):
        pairs = [
            (tactic in r.jixia_tactics, tactic in r.matched_tactics)
            for r in located
        ]
        both = sum(j and m for j, m in pairs)
        j_only = sum(j and not m for j, m in pairs)
        m_only = sum(m and not j for j, m in pairs)
        union = both + j_only + m_only
        rows.append({
            "tactic": tactic,
            "jixia_rate": sum(j for j, _ in pairs) / len(located),
            "matcher_rate": sum(m for _, m in pairs) / len(located),
            "both": both,
            "jixia_only": j_only,
            "matcher_only": m_only,
            # Jaccard. 1.0 means the instruments are interchangeable for this
            # tactic; low values mean its rate is not comparable across
            # corpora, because the corpora were measured with different ones.
            "agreement": both / union if union else float("nan"),
        })
    frame = pd.DataFrame(rows)
    frame.attrs["located"] = len(located)
    frame.attrs["total"] = len(records)
    return frame


def instrument_comparison_census() -> dict[str, float]:
    """Human any-automation rate under each instrument, CENSUS, paired.

    The number that matters for amendment 2: how much of the machine-vs-human
    0.464 gap is the instrument change rather than the corpus change. Both
    rates are computed over the SAME declarations — every eligible mathlib
    tactic proof whose body could be located — so the difference is purely
    instrument.
    """
    g = _explicit_graph()
    usage = load.load_tactic_usage()
    index, seen = _human_matcher_index()

    names = [n for n in eligible_declarations(g) if n in index]
    jixia = sum(bool(classes_used(usage.get(n, []))) for n in names)
    matcher = sum(bool(classes_used(index[n])) for n in names)
    return {
        "declarations": len(names),
        "located_fraction": len(names) / seen,
        "human_any_automation_jixia": jixia / len(names),
        "human_any_automation_matcher": matcher / len(names),
        "instrument_component": (matcher - jixia) / len(names),
    }


# --- entry point ---------------------------------------------------------

def main(cap: int = CLASS_SAMPLE_CAP) -> None:
    print("=" * 74)
    print("AMENDMENT 2 — instrument calibration, census")
    print("=" * 74)
    cen = instrument_comparison_census()
    print(f"eligible declarations with a located body : "
          f"{int(cen['declarations']):,} ({cen['located_fraction']:.3f})")
    print(f"human any-automation, jixia               : "
          f"{cen['human_any_automation_jixia']:.3f}")
    print(f"human any-automation, matcher             : "
          f"{cen['human_any_automation_matcher']:.3f}")
    print(f"instrument component of the 0.464 gap     : "
          f"{cen['instrument_component']:+.3f}")

    print()
    print("=" * 74)
    print(f"class-targeted human sample (cap {cap} per marginal matcher class)")
    print("=" * 74)
    records, population = collect_by_class(cap)
    print(f"usable declarations: {len(records)}")
    for cls in ALL_CLASSES:
        n = population[cls]
        print(f"  {cls:<8} population {n:>6}"
              f"{'  (censused)' if n <= cap else '  (sampled)'}")

    print()
    print("=" * 74)
    print("AMENDMENT 2b — string matcher vs jixia, per tactic, same declarations")
    print("=" * 74)
    calib = calibration(records)
    print(calib.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\nNOTE: the rate columns are over the CLASS-TARGETED sample, which "
          "over-represents\n      rare classes by construction. Read the "
          "agreement column, not the rates;\n      the corpus-level rates are "
          "the census figures printed above.")

    print()
    print("=" * 74)
    print("RECOVERY INSTRUMENT — ceiling matcher vs real extractor, same records")
    print("=" * 74)
    ct, ch = sum(r.targets for r in records), sum(r.hits for r in records)
    eh = sum(r.hits_extractor for r in records)
    rh = sum(r.hits_reachable for r in records)
    print(f"mathematical targets in the sample : {ct:,}")
    print(f"aggregate miss, ceiling matcher (file scope, substring) : "
          f"{1 - ch / ct:.4f}")
    print(f"aggregate miss, reachable bound (decl scope, substring) : "
          f"{1 - rh / ct:.4f}")
    print(f"aggregate miss, real extractor  (decl scope, resolver)  : "
          f"{1 - eh / ct:.4f}")
    print(f"ratio extractor / ceiling          : "
          f"{(1 - eh / ct) / (1 - ch / ct):.3f}x")
    print("NOTE: this sample is CLASS-TARGETED, so its aggregate is not the "
          "audit's\n      0.2085/0.3876 — those are a length-stratified draw. "
          "The ratio is\n      the comparable quantity.")

    print()
    print("=" * 74)
    print("AMENDMENT 1a — per-class miss rates, MARGINAL (classes overlap)")
    print("=" * 74)
    marginal = pd.concat(
        [marginal_miss_rates(records, population, hits_of=h_of)
         for h_of in (EXTRACTOR_HITS, REACHABLE_HITS, CEILING_HITS)],
        ignore_index=True,
    )
    print(marginal.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    defined = marginal[marginal["instrument"] == "extractor"]["miss_rate"].dropna()
    print(f"\nspread across classes (extractor): {defined.max() - defined.min():.3f}")

    print()
    print("=" * 74)
    print("AMENDMENT 1b — per-class miss rates, PARTITION "
          f"({'>'.join(config.TACTIC_CLASS_PRECEDENCE)})")
    print("=" * 74)
    partition = pd.concat(
        [partition_miss_rates(records, hits_of=h_of)
         for h_of in (EXTRACTOR_HITS, REACHABLE_HITS, CEILING_HITS)],
        ignore_index=True,
    )
    print(partition.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    print()
    print("=" * 74)
    print("AMENDMENT 1c — standardized imputed miss gap (REAL EXTRACTOR)")
    print("=" * 74)
    human_mix = human_class_mix_census()
    machine_mix = machine_class_mix()
    jixia_mix = human_class_mix_census(instrument="jixia")
    print(f"{'class':<10}{'human (matcher)':>18}{'machine (matcher)':>20}"
          f"{'human (jixia)':>16}")
    for cls in ALL_CLASSES:
        print(f"{cls:<10}{human_mix[cls]:>18.4f}{machine_mix[cls]:>20.4f}"
              f"{jixia_mix[cls]:>16.4f}")

    h, m, gap = standardized_gap(records, human_mix, machine_mix)
    lo, hi = bootstrap_gap(records, human_mix, machine_mix)
    print(f"\nimputed human miss rate   : {h:.4f}")
    print(f"imputed machine miss rate : {m:.4f}")
    print(f"standardized gap          : {gap:+.4f}  "
          f"[{lo:+.4f}, {hi:+.4f}] {config.H2_BOOTSTRAP_CI:.0%} CI")

    _, _, gap_ceiling = standardized_gap(
        records, human_mix, machine_mix, hits_of=CEILING_HITS
    )
    print(f"same design, ceiling matcher (superseded): {gap_ceiling:+.4f}")

    _, _, gap_jixia = standardized_gap(
        records, jixia_mix, machine_mix, tactics_of=JIXIA_TACTICS
    )
    print(f"jixia-strata sensitivity: {gap_jixia:+.4f}")

    print()
    print("decomposition — what moved the 2026-08-13 figure of +0.039:")
    decomp = decomposition(records, human_mix, machine_mix, jixia_mix)
    print(decomp.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    print()
    print("precedence sensitivity (24 orderings, both instruments):")
    sens = pd.concat(
        [precedence_sensitivity(records, hits_of=h_of)
         for h_of in (EXTRACTOR_HITS, REACHABLE_HITS, CEILING_HITS)],
        ignore_index=True,
    )
    ext = sens[sens["instrument"] == "extractor"]
    print(ext.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print(f"\nextractor band across orderings: "
          f"{ext['gap'].min():+.4f} to {ext['gap'].max():+.4f}")
    for label, key in (("reachable-bound band (diagnostic)", "reachable_bound"),
                       ("ceiling-matcher band (superseded)", "ceiling_matcher")):
        sub = sens[sens["instrument"] == key]
        print(f"{label}: {sub['gap'].min():+.4f} to {sub['gap'].max():+.4f}")

    _write(records, population, marginal, partition, calib, cen,
           human_mix, machine_mix, jixia_mix, h, m, gap, lo, hi, gap_jixia,
           ext, decomp, sens, gap_ceiling)


def _write(records, population, marginal, partition, calib, cen,
           human_mix, machine_mix, jixia_mix, h, m, gap, lo, hi,
           gap_jixia, sens, decomp, sens_all, gap_ceiling) -> None:
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    pd.concat([marginal, partition], ignore_index=True).to_csv(
        config.RESULTS / "miss_rate_by_tactic_class.csv", index=False)
    calib.to_csv(config.RESULTS / "instrument_calibration.csv", index=False)
    sens_all.to_csv(config.RESULTS / "precedence_sensitivity.csv", index=False)
    decomp.to_csv(config.RESULTS / "instrument_gap_decomposition.csv", index=False)

    pd.DataFrame([
        {"corpus": "human_mathlib", "instrument": "matcher", "basis": "census",
         **human_mix},
        {"corpus": "machine_goedel", "instrument": "matcher", "basis": "census",
         **machine_mix},
        {"corpus": "human_mathlib", "instrument": "jixia", "basis": "census",
         **jixia_mix},
    ]).to_csv(config.RESULTS / "tactic_class_mix.csv", index=False)

    pd.DataFrame([{
        "recovery_instrument": "extractor",
        "sampled_declarations": len(records),
        "arith_population": population["arith"],
        "decide_population": population["decide"],
        "located_fraction": cen["located_fraction"],
        "human_any_automation_jixia": cen["human_any_automation_jixia"],
        "human_any_automation_matcher": cen["human_any_automation_matcher"],
        "instrument_component": cen["instrument_component"],
        "imputed_human_miss": h,
        "imputed_machine_miss": m,
        "standardized_gap": gap,
        "ci_low": lo,
        "ci_high": hi,
        "standardized_gap_jixia_human": gap_jixia,
        "gap_min_over_precedence": sens["gap"].min(),
        "gap_max_over_precedence": sens["gap"].max(),
        "standardized_gap_ceiling_matcher": gap_ceiling,
    }]).to_csv(config.RESULTS / "instrument_reference.csv", index=False)
    print(f"\nwrote 6 CSVs to {config.RESULTS}")


if __name__ == "__main__":
    import sys

    main(int(sys.argv[1]) if len(sys.argv) > 1 else CLASS_SAMPLE_CAP)
