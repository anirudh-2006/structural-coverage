"""One extraction pass over both corpora, cached, so every downstream
analysis reads the SAME premise sets.

WHY THIS EXISTS. `analysis.length_overlap` re-extracts 70,086 mathlib
declarations and 29,750 Goedel proofs every time it runs, which made the
common-support design of `notes/changes/2026-08-17-e3-design.md` expensive to
iterate on and — worse — made it possible for two analyses to disagree because
they extracted differently. The records here are built once and cached under
`data/`, which is gitignored, so nothing here is hand-editable (CLAUDE.md §6).

WHAT A RECORD CARRIES. Enough to re-derive every stratification the project
uses without touching the source again: the wrap-invariant length (tactic
steps), the character length (retained as the sensitivity axis), the matcher
tactic set that assigns the partition class, and the resolved premise set.

ONE-SIDED CONTAMINATION IS RECORDED, NOT SILENTLY REMOVED. Two identifier
classes resolve on the human side and cannot resolve on the machine side:

  * the declaration's OWN NAME. Extraction runs at declaration scope, so
    `theorem Foo.bar : ...` puts `Foo.bar` in its own premise set. A
    declaration is never its own explicit dependency, so this is a pure false
    positive. It fires on 98.4% of human declarations and on 0% of machine
    proofs, whose `lean_workbook_*` names are not mathlib declarations.
  * the `lemma` KEYWORD, which is a real mathlib declaration
    (`Mathlib.Tactic.Lemma`, kind `definition`). Every mathlib source file
    that writes `lemma` resolves it. Goedel proofs are all written `theorem`,
    which is core syntax and not a declaration.

Both inflate the HUMAN premise vocabulary only, and the primary result
(`notes/changes/2026-08-17-coverage-primary.md`) is a human-vs-machine
vocabulary ratio. The flags are carried per record so the coverage numbers can
be reported under a stated exclusion rather than assumed clean.
"""

from __future__ import annotations

import pandas as pd

from src import config
from src.analysis import tactic_strata as ts
from src.analysis.automation_confound import GOEDEL_PARQUET
from src.analysis.spurious_symmetry import _theorem_name, machine_declaration_block
from src.extract import audit, decl_source
from src.extract import source as src_mod
from src.graph import load

HUMAN_CACHE = config.CENSUS_CACHE / "human_records.parquet"
MACHINE_CACHE = config.CENSUS_CACHE / "machine_records.parquet"

# The `lemma` keyword resolves to a real declaration. Named here rather than
# added to `audit._KEYWORDS`, because the keyword list is a property of the
# frozen extractor and this is a reporting-side exclusion whose effect must
# stay measurable. See the module docstring.
KEYWORD_DECLARATIONS = frozenset({"lemma"})


# --- build ----------------------------------------------------------------

def _build_human() -> pd.DataFrame:
    g = ts._explicit_graph()
    known = frozenset(load.declaration_names(g))
    tactic_index, block_index, _ = ts._human_census()

    rows = []
    for name in sorted(block_index):
        block = block_index[name]
        text = src_mod.read_module_source(g.nodes[name]["file_module"])
        found = audit.extract(block, known, decl_name=name, file_text=text)
        premises = found.resolved
        rows.append({
            "corpus": "human",
            "name": name,
            "chars": len(block),
            "steps": audit.tactic_steps(decl_source.proof_body(block)),
            "tactics": sorted(tactic_index.get(name, ())),
            "premises": sorted(premises),
            "via_prefix": len(found.via_prefix),
            "self_hit": name in premises,
            "keyword_hits": len(premises & KEYWORD_DECLARATIONS),
        })
    return pd.DataFrame(rows)


def _build_machine() -> pd.DataFrame:
    g = ts._explicit_graph()
    known = frozenset(load.declaration_names(g))
    df = pd.read_parquet(GOEDEL_PARQUET)

    rows = []
    for row in df.itertuples(index=False):
        block = machine_declaration_block(row.full_proof)
        if block is None:
            continue
        body = decl_source.proof_body(block)
        # decl_name must be non-empty or `audit.extract` skips prefix
        # resolution entirely, including the corpus header's `open` lines —
        # the machine side's only prefix source. Same call shape as
        # `analysis.spurious_symmetry`, so the two see identical premise sets.
        decl_name = _theorem_name(block)
        found = audit.extract(
            block, known, decl_name=decl_name, file_text=row.full_proof)
        premises = found.resolved
        rows.append({
            "corpus": "machine",
            "name": str(row.problem_id),
            "chars": len(block),
            "steps": audit.tactic_steps(body),
            "tactics": sorted(ts.automation_tactics_in_text(body)),
            "premises": sorted(premises),
            "via_prefix": len(found.via_prefix),
            "self_hit": decl_name in premises,
            "keyword_hits": len(premises & KEYWORD_DECLARATIONS),
        })
    return pd.DataFrame(rows)


_BUILDERS = {"human": (_build_human, HUMAN_CACHE),
             "machine": (_build_machine, MACHINE_CACHE)}


def census(corpus: str, rebuild: bool = False) -> pd.DataFrame:
    """Cached extraction census for one corpus."""
    build, path = _BUILDERS[corpus]
    if path.exists() and not rebuild:
        return pd.read_parquet(path)
    frame = build()
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return frame


# --- premise-set views ----------------------------------------------------

def premise_sets(
    frame: pd.DataFrame,
    drop_self: bool = True,
    drop_keywords: bool = True,
) -> list[frozenset[str]]:
    """Per-proof premise sets under a stated exclusion policy.

    Defaults drop both one-sided contaminants. `drop_self=False,
    drop_keywords=False` reproduces the 2026-08-17 numbers exactly.
    """
    out = []
    for name, premises in zip(frame["name"], frame["premises"]):
        s = set(premises)
        if drop_self:
            s.discard(name)
        if drop_keywords:
            s -= KEYWORD_DECLARATIONS
        out.append(frozenset(s))
    return out


def vocabulary(frame: pd.DataFrame, **kw) -> frozenset[str]:
    return frozenset().union(*premise_sets(frame, **kw)) if len(frame) else frozenset()


def main() -> None:
    for corpus in ("human", "machine"):
        frame = census(corpus, rebuild=True)
        raw = vocabulary(frame, drop_self=False, drop_keywords=False)
        clean = vocabulary(frame)
        print(f"{corpus:<8} {len(frame):>7,} proofs   "
              f"vocab raw {len(raw):>7,}  clean {len(clean):>7,}   "
              f"self-hit {frame['self_hit'].mean():.3f}  "
              f"keyword-hit {(frame['keyword_hits'] > 0).mean():.3f}")


if __name__ == "__main__":
    main()
