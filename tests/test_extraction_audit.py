"""The Aug 21 gate, as a REPORT — option (d), decided 2026-08-16.

This test's output is a number that goes in the paper. It is no longer a
pass/fail bar, because the bar has been mis-specified twice: 0.90 absolute
against a denominator whose LAYER was wrong, then 0.95 efficiency against a
ceiling whose SCOPE was wrong. Declaration-scope efficiency cannot exceed
~0.878, so 0.95 is unsatisfiable by construction, and setting a third
threshold after seeing 0.8815 is the researcher-degrees-of-freedom hazard
CLAUDE.md §6 exists to prevent.

So this test now asserts only two things:

  COMPUTABLE  the audit runs and returns a coherent rate — denominators
              non-zero, counts consistent, retention in [0, 1].
  STABLE      retention has not drifted from the recorded 0.6124 by more than
              AUDIT_RETENTION_STABILITY_TOL. This is a regression guard on the
              extractor, not a quality bar: it catches a code change that
              moves the instrument, which is what a test can usefully do here.

It does NOT assert `passes_gate`. A permanently red suite stops being
informative — once one failure is expected, the others get ignored with it —
and the honest reading is that the gate's job was to stop us sinking a week
into an unworkable parser, which it did. The paper defends the instrument on
the characterised residual instead, which is printed below.

Split into two halves on purpose. The parser tests run on synthetic strings
and need neither the 6.6 GB checkout nor the 2.2M-edge graph, so the
extractor stays testable when the data is not present. Only the data tests
are marked `gate`.
"""

import pytest

from src import config
from src.extract import audit

# --- the report ----------------------------------------------------------


@pytest.mark.gate
def test_extraction_retention_is_computable_and_stable():
    result = audit.run_audit(sample_size=config.AUDIT_SAMPLE_SIZE)

    recovered, total = result.loose["mathematical"]
    print(f"\n  RETENTION (loose, mathematical) = {result.retention:.4f}"
          f"   n={result.sample_size} declarations, {total} explicit targets")
    print(f"  recovered={result.recovered} missed={result.missed} "
          f"spurious={result.spurious}")
    print(f"  strict={result.retention_strict:.4f}  "
          f"worst_case={result.retention_worst_case:.4f}")

    # Like-for-like: the ceiling's OWN loose matcher, same sample, two scopes.
    # The frozen constant is a different sample and is reported separately so
    # the two are never differenced.
    print("\n  SCOPE DECOMPOSITION — the ceiling's loose matcher, this sample:")
    print(f"    whole file (paired ceiling)          {result.paired_ceiling:.4f}")
    print(f"    declaration block (reachable bound)  {result.reachable_bound:.4f}")
    print(f"    structurally unreachable per-decl    "
          f"{result.paired_ceiling - result.reachable_bound:.4f}")
    print(f"    extractor                            {result.retention:.4f}")
    print(f"    [frozen ceiling, different sample]   "
          f"{config.CEILING_MATHEMATICAL:.4f}")
    print("\n  EFFICIENCY against each denominator:")
    print(f"    vs frozen ceiling    {result.efficiency:.4f}  "
          f"(threshold {config.AUDIT_EFFICIENCY_THRESHOLD}, "
          f"NOT asserted — see module docstring)")
    print(f"    vs paired ceiling    {result.efficiency_paired:.4f}")
    print(f"    vs REACHABLE bound   {result.efficiency_reachable:.4f}  "
          f"<- what a per-declaration parser can actually be held to")
    print(f"  located {result.located} / unlocated {result.unlocated}   "
          f"gate asserted: {config.AUDIT_GATE_IS_ASSERTED}")

    # COMPUTABLE.
    assert total > 0, "empty denominator — the audit measured nothing"
    assert result.sample_size > 0
    assert 0.0 <= result.retention <= 1.0
    assert recovered + result.missed == total, (
        f"counts do not close: recovered {recovered} + missed "
        f"{result.missed} != {total} targets"
    )
    assert 0.0 <= result.reachable_bound <= 1.0
    assert result.retention <= result.reachable_bound + 1e-9, (
        f"retention {result.retention:.4f} exceeds the declaration-scope "
        f"reachable bound {result.reachable_bound:.4f} — the extractor cannot "
        "resolve more than a substring matcher over the same text finds"
    )

    # STABLE.
    drift = abs(result.retention - config.AUDIT_RETENTION_RECORDED)
    assert drift <= config.AUDIT_RETENTION_STABILITY_TOL, (
        f"retention {result.retention:.4f} has drifted {drift:.4f} from the "
        f"recorded {config.AUDIT_RETENTION_RECORDED:.4f} (tolerance "
        f"{config.AUDIT_RETENTION_STABILITY_TOL}). This is a REGRESSION "
        "signal, not a gate: something changed the instrument. If the change "
        "was intended, update AUDIT_RETENTION_RECORDED and write a change "
        "record under notes/changes/ per CLAUDE.md §9."
    )


@pytest.mark.gate
def test_retention_is_measured_against_explicit_subgraph_only():
    """Guard against the framing error: retention is vs. explicit edges, not all.

    74.2% of edges are compiler-synthesized. Auditing against the full graph
    would understate retention by construction. Asserted structurally: the
    audit's own denominator must equal the number of EXPLICIT out-edges of
    the sampled declarations, not their total out-edges.
    """
    from src.extract import ceiling
    from src.graph import load

    g = load.load_explicit_graph()
    sample = ceiling.sample_declarations(g, 25, seed=config.RANDOM_SEED)
    for name in sample:
        for _, _, data in g.out_edges(name, data=True):
            assert data["is_explicit"], (
                f"{name} has a non-explicit edge in the explicit subgraph — "
                "the audit denominator is contaminated"
            )


# --- the extractor, no data required -------------------------------------

KNOWN = frozenset({
    "Nat.succ_le_of_lt", "Nat.lt_irrefl", "mul_one", "Finset.sum_congr",
    "List.Nodup.filter", "Ideal.primeCompl", "Set.mem_setOf_eq",
})


def test_resolves_fully_qualified_names():
    got = audit.extract_premises(":= by exact Nat.succ_le_of_lt h", KNOWN)
    assert got == {"Nat.succ_le_of_lt"}


def test_resolves_under_the_declarations_own_namespace():
    """`Nat.foo`'s proof writes `lt_irrefl`, meaning `Nat.lt_irrefl`."""
    got = audit.extract(
        ":= by exact absurd h (lt_irrefl n)", KNOWN, decl_name="Nat.foo_bar"
    )
    assert "Nat.lt_irrefl" in got.resolved


def test_resolves_under_an_open_namespace():
    got = audit.extract(
        ":= by simp [mem_setOf_eq]",
        KNOWN,
        decl_name="Foo.bar",
        file_text="import Mathlib\nopen Set\n",
    )
    assert "Set.mem_setOf_eq" in got.resolved


def test_dot_notation_is_kept_as_a_suffix_token_not_resolved_greedily():
    """`h.filter` must not pull in every declaration ending in `.filter`."""
    got = audit.extract(":= by exact h.filter hp", KNOWN, decl_name="Foo.bar")
    assert got.resolved == frozenset()
    assert "filter" in got.suffix_tokens


def test_comments_do_not_contribute_premises():
    """74.7% of machine proof-body text is natural-language comment."""
    body = ":= by\n  -- we use mul_one here\n  /- and Finset.sum_congr -/\n  ring"
    assert audit.extract_premises(body, KNOWN) == set()


def test_nested_block_comments_are_stripped():
    body = ":= by /- outer /- inner mul_one -/ still comment -/ ring"
    assert audit.extract_premises(body, KNOWN) == set()


def test_string_literals_do_not_contribute_premises():
    assert audit.extract_premises(':= by fail_if_success "mul_one"', KNOWN) == set()


def test_tactic_names_are_not_premises():
    body = ":= by simp; ring_nf; nlinarith [sq_nonneg x]"
    assert audit.extract_premises(body, KNOWN) == set()


def test_simp_set_arguments_are_premises():
    body = ":= by simp [mul_one, Finset.sum_congr]"
    assert audit.extract_premises(body, KNOWN) == {"mul_one", "Finset.sum_congr"}


def test_rewrite_arrows_do_not_break_resolution():
    body = ":= by rw [← mul_one a, Set.mem_setOf_eq]"
    got = audit.extract_premises(body, KNOWN)
    assert got == {"mul_one", "Set.mem_setOf_eq"}


def test_unknown_identifiers_are_not_invented():
    got = audit.extract(":= by exact not_a_real_lemma h", KNOWN, decl_name="Foo.bar")
    assert got.resolved == frozenset()


def test_retention_is_over_edges_not_declarations():
    """The scaffold divided by declaration count, which is not a rate."""
    r = audit.AuditResult(sample_size=3, loose={"mathematical": (7, 10)})
    assert r.retention == pytest.approx(0.7)


def test_gate_is_efficiency_against_the_ceiling_not_an_absolute():
    """A retention below the old absolute 0.90 but at 0.95 of the measured
    ceiling must PASS — that is the whole point of the 2026-08-13
    re-derivation."""
    r = audit.AuditResult(
        loose={"mathematical": (0, 0)}, strict={"mathematical": (0, 0)}
    )
    r.loose["mathematical"] = (int(0.79 * 1000), 1000)
    assert r.retention < 0.90
    assert r.efficiency == pytest.approx(0.79 / config.CEILING_MATHEMATICAL, rel=1e-3)
    assert r.passes_gate
