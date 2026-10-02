"""Loading and the two-layer split.

The layer partition fixes the audit's gate denominator, so a regression here
silently changes the number that goes in the paper.
"""

import pytest

from src import config
from src.graph import load


@pytest.fixture(scope="module")
def g():
    return load.load_explicit_graph()


@pytest.fixture(scope="module")
def layers(g):
    return load.split_hub_layers(g)


def test_explicit_subgraph_matches_published_counts(g):
    summary = load.graph_summary()["declaration_graph"]
    assert g.number_of_nodes() == config.EXPECTED_DECL_NODES
    assert g.number_of_edges() == summary["explicit_edge_count"]
    assert g.number_of_edges() == config.EXPECTED_EXPLICIT_EDGES


def test_explicit_is_a_minority_of_the_full_graph():
    """74.2% of edges are compiler-synthesized (CLAUDE.md §4)."""
    summary = load.graph_summary()["declaration_graph"]
    ratio = summary["explicit_edge_count"] / summary["edge_count_raw"]
    assert ratio == pytest.approx(summary["explicit_edge_ratio"], abs=1e-4)
    assert ratio < 0.30


@pytest.mark.parametrize(
    "name",
    [
        "propext",           # axiom, empty file_module
        "of_eq_true",        # kind == theorem, so `kind` alone misses it
        "funext",            # kind == theorem
        "Classical.choice",  # axiom under a non-obvious namespace
        "Eq.mpr",            # inserted by `rw`, never typed
        "Eq.refl",
        "outParam",
        "AddSemigroup.toAdd",  # is_instance, and IS in a Mathlib file
    ],
)
def test_elaborator_constants_are_language_infrastructure(layers, name):
    """The bug this guards: prefix matching classified these as mathematical.

    They carry explicit in-edges in the tens of thousands while being typed by
    nobody, so counting them as mathematical inflates the gate denominator
    with targets no source parser can ever recover.
    """
    infrastructure, mathematical = layers
    assert name in infrastructure, f"{name} must not count as mathematical"
    assert name not in mathematical


def test_real_mathematics_is_not_swept_into_infrastructure(layers):
    """The converse failure: prefix matching over-captured real mathlib results.

    Decidable.* theorems are genuine mathematics living in Mathlib files;
    INFRASTRUCTURE_NAMESPACE_PREFIXES contains "Decidable" and would exclude
    them from the denominator.
    """
    _, mathematical = layers
    assert "Decidable.eq_or_ne" in mathematical


def test_partition_is_a_partition(g, layers):
    infrastructure, mathematical = layers
    assert not (infrastructure & mathematical)
    assert infrastructure | mathematical == set(g.nodes)


def test_mathematical_layer_is_the_bulk_of_the_library(layers):
    """Sanity floor. A partition assigning ~everything to one side is broken.

    This caught a real defect: pandas `usecols` returns columns in file order,
    not the order requested, so node attributes were shifted by one column and
    99.8% of declarations landed in infrastructure.
    """
    infrastructure, mathematical = layers
    total = len(infrastructure) + len(mathematical)
    assert 0.6 < len(mathematical) / total < 0.95
