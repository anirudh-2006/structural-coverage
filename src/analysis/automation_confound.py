"""Does the extraction blind spot scale with automation, and is the machine
corpus automation-heavy?

Motivation. The ceiling analysis showed source-visible extraction misses ~18%
of mathematical-layer explicit edges, and every residual class is an
automation artifact: simp-set lemmas fired without being named, tactic-emitted
term constants, notation-backed definitions. If that blind spot grows with
automation AND machine proofs use more automation than human ones, then H2's
effect could be manufactured by the instrument rather than observed in the
data. Flat-across-proof-length does not address this — length and automation
are different axes.

Run BEFORE building the parser. Nothing here is an H2 metric; this is
instrument validation, and it looks at the machine corpus only to characterise
a confound (CLAUDE.md §6 freezes metric definitions, which do not yet exist).
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pandas as pd

from src import config
from src.extract import ceiling, decl_source
from src.extract import source as src_mod
from src.graph import load

GOEDEL_PARQUET = (
    config.DATA / "machine_proofs" / "goedel_lean_workbook"
    / "data" / "train-00000-of-00001.parquet"
)

_TACTIC_PATTERNS = {
    t: re.compile(rf"(?<![A-Za-z0-9_'!?.]){re.escape(t)}(?![A-Za-z0-9_'!?])")
    for t in config.AUTOMATION_TACTICS
}


def automation_tactics_in_text(text: str) -> set[str]:
    """Automation tactic names occurring as tokens in proof source."""
    return {t for t, p in _TACTIC_PATTERNS.items() if p.search(text)}


def human_ceiling_by_automation(sample_size: int = 500) -> pd.DataFrame:
    """Ceiling, split by whether the human proof uses automation at all.

    Uses the publishers' own jixia-extracted tactic lists, not string matching.
    """
    g = load.load_explicit_graph()
    _, mathematical = load.split_hub_layers(g)
    usage = load.load_tactic_usage()

    rows: dict[str, Counter] = {
        "automation": Counter(), "none": Counter(),
    }
    for decl in ceiling.sample_declarations(g, sample_size):
        text = src_mod.read_module_source(g.nodes[decl]["file_module"])
        if text is None:
            continue
        stratum = load.automation_stratum(usage.get(decl, []))
        for target in g.successors(decl):
            if target not in mathematical:
                continue
            rows[stratum]["total"] += 1
            rows[stratum]["hit"] += ceiling.name_or_suffix_occurs(target, text)
        rows[stratum]["decls"] += 1

    return pd.DataFrame(
        [
            {
                "stratum": k,
                "declarations": c["decls"],
                "targets": c["total"],
                "ceiling": c["hit"] / c["total"] if c["total"] else float("nan"),
                "miss_rate": 1 - c["hit"] / c["total"] if c["total"] else float("nan"),
            }
            for k, c in rows.items()
        ]
    )


def _proof_body(full_proof: str) -> str:
    """Everything after the first top-level `:=`, i.e. drop the statement.

    Crude, and good enough for counting tactic tokens: tactic names do not
    appear in Lean Workbook statements.

    Delegates to decl_source so the human and machine sides are guaranteed to
    be cut by the SAME rule — the instrument calibration compares them.
    """
    return decl_source.proof_body(full_proof)


def machine_automation_distribution() -> tuple[pd.DataFrame, float]:
    """Automation-tactic usage across Goedel-LM/Lean-workbook-proofs."""
    df = pd.read_parquet(GOEDEL_PARQUET)
    bodies = df["full_proof"].map(_proof_body)
    found = bodies.map(automation_tactics_in_text)

    counts = Counter()
    for s in found:
        counts.update(s)
    any_rate = float((found.map(len) > 0).mean())

    dist = pd.DataFrame(
        sorted(counts.items(), key=lambda kv: -kv[1]),
        columns=["tactic", "proofs"],
    )
    dist["share"] = dist["proofs"] / len(df)
    return dist, any_rate


def human_automation_rate() -> float:
    """Share of sampled human tactic proofs using any automation tactic."""
    g = load.load_explicit_graph()
    usage = load.load_tactic_usage()
    sample = ceiling.sample_declarations(g, 2000)
    strata = [load.automation_stratum(usage.get(d, [])) for d in sample]
    return strata.count("automation") / len(strata)


def main() -> None:
    print("=" * 68)
    print("1. HUMAN — does the extraction blind spot scale with automation?")
    print("=" * 68)
    by_auto = human_ceiling_by_automation()
    print(by_auto.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    print()
    print("=" * 68)
    print("2. MACHINE — automation in Goedel-LM/Lean-workbook-proofs")
    print("=" * 68)
    dist, any_rate = machine_automation_distribution()
    print(dist.head(12).to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    h_rate = human_automation_rate()
    print()
    print(f"any automation tactic — machine : {any_rate:.3f}")
    print(f"any automation tactic — human   : {h_rate:.3f}")
    print(f"gap                             : {any_rate - h_rate:+.3f}")

    config.RESULTS.mkdir(parents=True, exist_ok=True)
    by_auto.to_csv(config.RESULTS / "ceiling_by_automation.csv", index=False)
    dist.to_csv(config.RESULTS / "machine_automation_distribution.csv", index=False)
    Path(config.RESULTS / "automation_rates.csv").write_text(
        "corpus,any_automation_rate\n"
        f"human_mathlib,{h_rate:.4f}\nmachine_goedel,{any_rate:.4f}\n"
    )
    print(f"\nwrote 3 CSVs to {config.RESULTS}")


if __name__ == "__main__":
    main()
