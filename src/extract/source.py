"""Locating declaration source text in the mathlib4 checkout.

The published graph ships no statements and no proof bodies, so source-visible
extraction reads the .lean files directly, at the commit the graph was built
from (config.MATHLIB_COMMIT_FULL). Nothing here compiles Lean.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src import config


def module_to_path(file_module: str) -> Path:
    """'Mathlib.Algebra.Group.Defs' -> <src>/Mathlib/Algebra/Group/Defs.lean"""
    return config.MATHLIB_SRC / (file_module.replace(".", "/") + ".lean")


@lru_cache(maxsize=512)
def read_module_source(file_module: str) -> str | None:
    """Full text of a module, or None if it is not in the checkout.

    Declarations from Lean core / Batteries have no Mathlib file and return
    None; callers treat that as "not source-visible here" rather than an error.
    """
    path = module_to_path(file_module)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")
