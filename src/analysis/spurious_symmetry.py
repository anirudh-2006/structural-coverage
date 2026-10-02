"""Is the extractor's FALSE-POSITIVE rate symmetric across the two corpora?

The audit reports 1,146 spurious resolutions and never gates on them
(notes/changes/2026-08-16-extraction-audit-first-run.md, "Known artifacts").
Not gating is right — tuning precision after seeing the gate number is the
§6 hazard. But leaving them unanalysed is a different thing, because
precision enters H2 the same way recall does:

  * a MISSED premise makes a proof look structurally NARROWER
  * a SPURIOUS premise makes it look structurally BROADER

So the two instrument artifacts run in OPPOSITE directions. The miss artifact
is already measured and pushes in H2's own predicted direction
(H2_INSTRUMENT_REFERENCE). If spurious resolutions are also asymmetric, they
partly offset it — and the net reference line is what H2 must clear, not the
miss component alone. An asymmetry either way has to be measured, not
assumed away.

WHAT CAN AND CANNOT BE MEASURED HERE. Machine proofs have no ground-truth
premise set — that is exactly what the A3 Lean pilot would buy — so the
machine spurious rate cannot be observed. Three things can:

  1. the human spurious rate, per tactic class and per resolution mechanism,
     against the published explicit subgraph;
  2. the RESOLUTION MECHANISM MIX on both corpora, which needs no ground
     truth at all: whether a resolved name was written fully-qualified or
     completed under a namespace / `open` prefix;
  3. two independent imputations of the machine rate, one standardizing the
     human per-class rate onto the machine class mix (the A1/A2 construction),
     one standardizing the human per-mechanism rate onto the machine
     mechanism mix.

Route 2 is the one that carries real weight, because the mechanism is what
actually manufactures a false positive: exact matching has nothing to get
wrong, prefix completion ignores the section scoping of `open`. And the
mechanism mix is a DIRECT measurement on both sides rather than a transfer.

A structural asymmetry is visible before any number is computed. Every Goedel
proof carries the same five-namespace header — `open BigOperators Real Nat
Topology Rat` — while a mathlib declaration sits inside its own namespace
with whatever the file opens. The prefix pool is therefore fixed and shallow
on the machine side and variable and deep on the human side. That is a
property of the released corpus, not of our parser, and it is why the
mechanism mix cannot be assumed equal.

Scope parity is enforced deliberately: the human side extracts from the
located DECLARATION BLOCK with the whole file as prefix context, so the
machine side extracts from the `theorem ...` line onward with the whole
`full_proof` (header included) as prefix context. Feeding the machine header
into the extraction scope instead would resolve `Real`, `Nat` and `Mathlib`
as premises in all 29,750 proofs and manufacture the asymmetry being tested.

Nothing here is an H2 metric and nothing here compiles Lean.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

import pandas as pd

from src import config
from src.analysis import tactic_strata as ts
from src.analysis.automation_confound import (
    GOEDEL_PARQUET,
    automation_tactics_in_text,
)
from src.extract import audit
from src.graph import load

# A Goedel `full_proof` is a standalone module: imports, `set_option`, an
# `open` line, a docstring, then the theorem. The declaration starts here.
_MACHINE_DECL = re.compile(r"^(?:theorem|lemma)\s", re.MULTILINE)

MACHINE_SAMPLE_SIZE = 4_000


def machine_declaration_block(full_proof: str) -> str | None:
    """The `theorem ...` block of a machine proof, header excluded.

    The human-side analogue is `decl_source.block_from_file_index`, which also
    returns statement + proof and also excludes everything above it. Keeping
    the header would put `Mathlib`, `Aesop`, `Real`, `Nat` and `Topology` into
    the extraction scope of every single machine proof.
    """
    m = _MACHINE_DECL.search(full_proof)
    return full_proof[m.start():] if m else None


@dataclass(frozen=True)
class MachineRecord:
    """One Goedel proof seen through the extractor. No ground truth exists."""

    problem_id: str
    tactic_class: str
    resolved: int
    resolved_exact: int
    resolved_prefix: int


def machine_records(
    known: frozenset[str],
    sample_size: int = MACHINE_SAMPLE_SIZE,
    seed: int = config.RANDOM_SEED,
) -> list[MachineRecord]:
    """Extract from a seeded sample of Goedel proofs, at declaration scope."""
    df = pd.read_parquet(GOEDEL_PARQUET)
    idx = list(range(len(df)))
    if sample_size < len(df):
        idx = sorted(random.Random(seed).sample(idx, sample_size))

    out: list[MachineRecord] = []
    for i in idx:
        row = df.iloc[i]
        full = row["full_proof"]
        block = machine_declaration_block(full)
        if block is None:
            continue
        name = _theorem_name(block)
        found = audit.extract(block, known, decl_name=name, file_text=full)
        out.append(MachineRecord(
            problem_id=str(row["problem_id"]),
            # Cut with the same string matcher and the same proof-body rule as
            # the human strata, so the class mix is instrument-matched.
            tactic_class=ts.assign_class(
                automation_tactics_in_text(_proof_part(block))
            ),
            resolved=len(found.resolved),
            resolved_exact=len(found.resolved) - len(found.via_prefix),
            resolved_prefix=len(found.via_prefix),
        ))
    return out


_THEOREM_NAME = re.compile(r"^(?:theorem|lemma)\s+([A-Za-z0-9_'!?.]+)")


def _theorem_name(block: str) -> str:
    m = _THEOREM_NAME.match(block)
    return m.group(1) if m else ""


def _proof_part(block: str) -> str:
    idx = block.find(":=")
    return block[idx:] if idx != -1 else block


# --- rates ---------------------------------------------------------------


def human_spurious_by_class(
    records: list[ts.DeclRecord],
    precedence=config.TACTIC_CLASS_PRECEDENCE,
) -> pd.DataFrame:
    """Spurious rate per PARTITION stratum, human side, against the graph.

    Denominator is resolved premises, not declarations: the quantity that
    matters downstream is "what fraction of what the extractor puts into a
    premise set does not belong there".
    """
    rows = []
    for cls in ts.ALL_CLASSES:
        sel = [r for r in records
               if ts.assign_class(r.matched_tactics, precedence) == cls]
        res = sum(r.resolved for r in sel)
        sp = sum(r.spurious for r in sel)
        rows.append({
            "class": cls, "declarations": len(sel), "resolved": res,
            "spurious": sp,
            "spurious_rate": sp / res if res else float("nan"),
        })
    return pd.DataFrame(rows)


def human_spurious_by_mechanism(records: list[ts.DeclRecord]) -> pd.DataFrame:
    """Spurious rate split by HOW the name resolved. The causal split."""
    rows = []
    for label, res_attr, sp_attr in (
        ("exact", "resolved_exact", "spurious_exact"),
        ("prefix", "resolved_prefix", "spurious_prefix"),
    ):
        res = sum(getattr(r, res_attr) for r in records)
        sp = sum(getattr(r, sp_attr) for r in records)
        rows.append({
            "mechanism": label, "resolved": res, "spurious": sp,
            "spurious_rate": sp / res if res else float("nan"),
        })
    return pd.DataFrame(rows)


def spurious_composition(records: list[ts.DeclRecord]) -> pd.DataFrame:
    """Split the human spurious set by whether the dependency exists at all.

    "Spurious" is measured against the EXPLICIT subgraph, and `is_explicit`
    is an elaborator property, not a statement about whether the declaration
    depends on the name (notes/decisions.md 2026-08-13 §1). So a resolution
    can be spurious in three quite different senses:

      implicit_edge   the declaration really does depend on the target; the
                      dependency is recorded in the full graph but carries no
                      explicit edge. The extractor read the source correctly
                      and the explicit subgraph is what excludes it. Arguably
                      not an error at all, and it CANNOT inflate a structural
                      metric with a nonexistent dependency.
      no_edge         no dependency of any kind. A genuine false positive:
                      scoping error in `open` resolution, a name mentioned in
                      a comment the stripper missed, a local shadowing a
                      global.
      (denominator)   every resolved name.

    Reads the full 8.4M-edge frame rather than building the full graph, which
    is several GB of networkx adjacency for a lookup that needs none.
    """
    edges = load.load_edge_frame()
    wanted = {r.name for r in records}
    sub = edges[edges["source"].isin(wanted)]
    all_dep: dict[str, set[str]] = {}
    for s, t in zip(sub["source"], sub["target"]):
        all_dep.setdefault(s, set()).add(t)

    g = ts._explicit_graph()
    known = frozenset(load.declaration_names(g))
    _, block_index, _ = ts._human_census()

    rows = []
    for r in records:
        block = block_index.get(r.name)
        if block is None:
            continue
        text = ts.src_mod.read_module_source(g.nodes[r.name]["file_module"])
        found = audit.extract(block, known, decl_name=r.name, file_text=text)
        explicit = set(g.successors(r.name))
        every = all_dep.get(r.name, set())
        for name in found.resolved - explicit:
            rows.append({
                "declaration": r.name,
                "kind": "implicit_edge" if name in every else "no_edge",
            })
    frame = pd.DataFrame(rows)
    return (
        frame.groupby("kind").size().rename("count").reset_index()
        if len(frame)
        else pd.DataFrame(columns=["kind", "count"])
    )


def mechanism_mix(resolved_exact: int, resolved_prefix: int) -> dict[str, float]:
    total = resolved_exact + resolved_prefix
    if not total:
        return {"exact": float("nan"), "prefix": float("nan")}
    return {"exact": resolved_exact / total, "prefix": resolved_prefix / total}


def machine_class_mix_from(records: list[MachineRecord]) -> dict[str, float]:
    counts = {c: 0 for c in ts.ALL_CLASSES}
    for r in records:
        counts[r.tactic_class] += 1
    return {c: n / len(records) for c, n in counts.items()}


# --- entry point ---------------------------------------------------------


def main(sample_size: int = MACHINE_SAMPLE_SIZE) -> None:
    g = ts._explicit_graph()
    known = frozenset(load.declaration_names(g))

    print("=" * 74)
    print("HUMAN SIDE — spurious resolutions against the explicit subgraph")
    print("=" * 74)
    human, _ = ts.collect_by_class()
    h_res = sum(r.resolved for r in human)
    h_sp = sum(r.spurious for r in human)
    print(f"declarations {len(human):,}   resolved {h_res:,}   "
          f"spurious {h_sp:,}   rate {h_sp / h_res:.4f}")

    by_class = human_spurious_by_class(human)
    print()
    print(by_class.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    by_mech = human_spurious_by_mechanism(human)
    print()
    print(by_mech.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    h_mech = mechanism_mix(
        sum(r.resolved_exact for r in human),
        sum(r.resolved_prefix for r in human),
    )

    print()
    print("=" * 74)
    print("WHAT 'SPURIOUS' CONTAINS — against the FULL graph, not just explicit")
    print("=" * 74)
    comp = spurious_composition(human)
    total = int(comp["count"].sum()) if len(comp) else 0
    for _, row in comp.iterrows():
        print(f"  {row['kind']:<16}{int(row['count']):>8,}"
              f"{row['count'] / total:>9.1%} of spurious"
              f"{row['count'] / h_res:>9.1%} of resolved")
    no_edge = int(comp.loc[comp["kind"] == "no_edge", "count"].sum())
    print(f"\ngenuine false-positive rate (no dependency of any kind): "
          f"{no_edge / h_res:.4f}")
    print(f"reported spurious rate (explicit subgraph only):          "
          f"{h_sp / h_res:.4f}")

    print()
    print("=" * 74)
    print(f"MACHINE SIDE — Goedel, n={sample_size:,}, declaration scope")
    print("=" * 74)
    machine = machine_records(known, sample_size)
    m_res = sum(r.resolved for r in machine)
    m_mech = mechanism_mix(
        sum(r.resolved_exact for r in machine),
        sum(r.resolved_prefix for r in machine),
    )
    print(f"proofs {len(machine):,}   resolved {m_res:,}   "
          f"per proof {m_res / len(machine):.2f}  "
          f"(human {h_res / len(human):.2f})")

    print()
    print("=" * 74)
    print("DIRECT MEASUREMENT — resolution mechanism mix (no ground truth "
          "needed)")
    print("=" * 74)
    print(f"{'mechanism':<12}{'human':>10}{'machine':>10}{'delta':>10}")
    for mech in ("exact", "prefix"):
        print(f"{mech:<12}{h_mech[mech]:>10.4f}{m_mech[mech]:>10.4f}"
              f"{m_mech[mech] - h_mech[mech]:>+10.4f}")

    print()
    print("=" * 74)
    print("IMPUTED machine spurious rate — two independent routes")
    print("=" * 74)
    class_rates = dict(zip(by_class["class"], by_class["spurious_rate"]))
    h_class_mix = ts.human_class_mix_census()
    m_class_mix = machine_class_mix_from(machine)
    imp_h_class = ts.standardize(class_rates, h_class_mix)
    imp_m_class = ts.standardize(class_rates, m_class_mix)

    mech_rates = dict(zip(by_mech["mechanism"], by_mech["spurious_rate"]))
    imp_h_mech = ts.standardize(mech_rates, h_mech)
    imp_m_mech = ts.standardize(mech_rates, m_mech)

    print("machine class mix (sample) : "
          + "  ".join(f"{c} {m_class_mix[c]:.3f}" for c in ts.ALL_CLASSES))
    print("machine class mix (census) : "
          + "  ".join(f"{c} {v:.3f}" for c, v in
                      ts.machine_class_mix().items()))
    print()
    print(f"{'route':<26}{'human':>10}{'machine':>10}{'gap':>10}")
    print(f"{'class standardization':<26}{imp_h_class:>10.4f}"
          f"{imp_m_class:>10.4f}{imp_m_class - imp_h_class:>+10.4f}")
    print(f"{'mechanism standardization':<26}{imp_h_mech:>10.4f}"
          f"{imp_m_mech:>10.4f}{imp_m_mech - imp_h_mech:>+10.4f}")

    print()
    print("=" * 74)
    print("DIRECTION — do the two instrument artifacts cancel or compound?")
    print("=" * 74)
    print("A MISSED premise narrows a proof; a SPURIOUS one broadens it. So a")
    print("machine spurious rate BELOW the human one narrows the machine side")
    print("further and COMPOUNDS the miss artifact. Above it would offset.")
    print()
    print(f"  miss artifact (H2_INSTRUMENT_REFERENCE)  "
          f"{config.H2_INSTRUMENT_REFERENCE:+.4f}   machine narrower")
    for label, gap in (("class route", imp_m_class - imp_h_class),
                       ("mechanism route", imp_m_mech - imp_h_mech)):
        print(f"  spurious artifact, {label:<21}{gap:+.4f}   "
              f"machine {'narrower — COMPOUNDS' if gap < 0 else 'broader — offsets'}")

    _write(by_class, by_mech, h_mech, m_mech, human, machine,
           h_res, h_sp, m_res, imp_h_class, imp_m_class, imp_h_mech, imp_m_mech,
           comp)


def _write(by_class, by_mech, h_mech, m_mech, human, machine,
           h_res, h_sp, m_res, imp_h_class, imp_m_class,
           imp_h_mech, imp_m_mech, comp) -> None:
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    by_class.to_csv(
        config.RESULTS / "spurious_by_class.csv", index=False)
    by_mech.to_csv(
        config.RESULTS / "spurious_by_mechanism.csv", index=False)
    comp.to_csv(
        config.RESULTS / "spurious_composition.csv", index=False)
    pd.DataFrame([
        {"corpus": "human_mathlib", "declarations": len(human),
         "resolved": h_res, "spurious": h_sp,
         "spurious_rate": h_sp / h_res,
         "resolved_per_decl": h_res / len(human),
         "mech_exact": h_mech["exact"], "mech_prefix": h_mech["prefix"],
         "imputed_spurious_class_route": imp_h_class,
         "imputed_spurious_mechanism_route": imp_h_mech},
        {"corpus": "machine_goedel", "declarations": len(machine),
         "resolved": m_res, "spurious": -1,
         "spurious_rate": float("nan"),
         "resolved_per_decl": m_res / len(machine),
         "mech_exact": m_mech["exact"], "mech_prefix": m_mech["prefix"],
         "imputed_spurious_class_route": imp_m_class,
         "imputed_spurious_mechanism_route": imp_m_mech},
    ]).to_csv(config.RESULTS / "spurious_symmetry.csv", index=False)
    print(f"\nwrote 4 CSVs to {config.RESULTS}")


if __name__ == "__main__":
    import sys

    main(int(sys.argv[1]) if len(sys.argv) > 1 else MACHINE_SAMPLE_SIZE)
