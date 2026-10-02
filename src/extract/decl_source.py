"""Locate a single declaration's source block inside its .lean file.

The ceiling analysis matches against WHOLE FILES on purpose — it wants an
upper bound. Instrument calibration cannot: every mathlib file mentions
`simp` somewhere, so whole-file tactic matching would report an automation
rate of ~1.0 for every human proof and measure nothing.

The published graph ships no source positions (metrics.csv carries
file_module but no line span), so the block is located textually. This is a
heuristic and its hit rate is measured, never assumed — see
`locate_rate` in analysis.instrument_calibration.

Nothing here compiles Lean.
"""

from __future__ import annotations

import re

from src.extract import source as src_mod

# Modifiers that may sit between the start of a line and the `theorem`
# keyword. Attribute brackets are allowed to nest one level of `[...]`.
_MODIFIERS = (
    r"(?:@\[[^\]]*\]\s*)*"
    r"(?:private\s+|protected\s+|nonrec\s+|noncomputable\s+|scoped\s+"
    r"|partial\s+|unsafe\s+)*"
)

# A line at column 0 starting one of these ends the preceding block. The set
# is deliberately broad: over-matching truncates a proof body (conservative,
# loses tactics at the tail), under-matching swallows the next declaration
# (anti-conservative, invents tactics). Prefer truncation.
_BLOCK_END = re.compile(
    r"^(?:@\[|/-|--|"
    r"(?:private|protected|nonrec|noncomputable|scoped|partial|unsafe)\s|"
    r"(?:theorem|lemma|def|abbrev|instance|example|structure|class|inductive|"
    r"namespace|end|section|variable|variables|open|attribute|alias|macro|"
    r"macro_rules|syntax|notation|elab|declare_config_elab|deriving|"
    r"set_option|universe|import|initialize|register_simp_attr|add_decl_doc)"
    r"(?:\s|$))"
)

_IDENT_TAIL = r"(?![A-Za-z0-9_'!?.])"


def name_candidates(name: str) -> list[str]:
    """Progressively shorter tails of a fully-qualified name.

    `List.Nodup.filter` is written `theorem Nodup.filter` inside
    `namespace List`, so the source form is not knowable from the name alone.
    Longest first, so the most specific match wins.
    """
    parts = name.split(".")
    return [".".join(parts[i:]) for i in range(len(parts))]


def locate_block(name: str, text: str) -> str | None:
    """The `theorem`/`lemma` block declaring `name`, statement included.

    Returns None when no declaration line matches — auto-generated instance
    names (`instIsScalarTowerTensorProduct_1`) have no textual declaration
    site and are the bulk of the misses.
    """
    lines = text.split("\n")
    for cand in name_candidates(name):
        pattern = re.compile(
            rf"^{_MODIFIERS}(?:theorem|lemma)\s+{re.escape(cand)}{_IDENT_TAIL}"
        )
        for i, line in enumerate(lines):
            if pattern.match(line):
                j = i + 1
                while j < len(lines):
                    ln = lines[j]
                    if ln and not ln[0].isspace() and _BLOCK_END.match(ln):
                        break
                    j += 1
                return "\n".join(lines[i:j])
    return None


def proof_body(block: str) -> str:
    """Everything from the first `:=` on, i.e. drop the statement.

    Same crude rule the machine side uses on Goedel `full_proof` strings, and
    it must stay the same rule — the whole point of the calibration is that
    both corpora meet the same instrument.
    """
    idx = block.find(":=")
    return block[idx:] if idx != -1 else block


def declaration_proof_body(name: str, file_module: str) -> str | None:
    """Proof body of a mathlib declaration, or None if it cannot be located."""
    text = src_mod.read_module_source(file_module)
    if text is None:
        return None
    block = locate_block(name, text)
    return None if block is None else proof_body(block)


_DECL_LINE = re.compile(
    rf"^{_MODIFIERS}(?:theorem|lemma)\s+([A-Za-z0-9_'!?.«»]+)"
)


def file_blocks(text: str) -> dict[str, str]:
    """Every theorem/lemma block in a file, keyed by the name AS WRITTEN.

    `locate_block` rescans the whole file per declaration, which is fine for a
    sample and quadratic for a census — mathlib has ~80k tactic proofs across
    7.5k files. This does one pass per file instead.

    The key is the source-form name (`Nodup.filter`), not the fully-qualified
    one, so callers resolve via `name_candidates`. On a duplicate source-form
    name within one file, the FIRST block wins; that is rare and only affects
    which of two same-named declarations a body is attributed to, not whether
    one is found.
    """
    lines = text.split("\n")
    starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _DECL_LINE.match(line)
        if m:
            starts.append((i, m.group(1)))

    blocks: dict[str, str] = {}
    for idx, (i, written) in enumerate(starts):
        limit = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        j = i + 1
        while j < limit:
            ln = lines[j]
            if ln and not ln[0].isspace() and _BLOCK_END.match(ln):
                break
            j += 1
        blocks.setdefault(written, "\n".join(lines[i:j]))
    return blocks


def block_from_file_index(name: str, blocks: dict[str, str]) -> str | None:
    """Resolve a fully-qualified name against a `file_blocks` index."""
    for cand in name_candidates(name):
        if cand in blocks:
            return blocks[cand]
    return None
