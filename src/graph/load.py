"""Load the mathlib dependency graph.

We do NOT rebuild this graph. It is published as part of arXiv:2604.24797
(HuggingFace: MathNetwork/MathlibGraph). See CLAUDE.md §4.

Our object of study is the EXPLICIT subgraph — the ~26% of edges visible in
source code, which the source paper identifies as the closer proxy for
human-intended dependencies. The other 74.2% are compiler-synthesized.

A caution that governs everything downstream: `is_explicit` in the published
data does NOT mean "written by a human". It is the `*` marker from
lean-training-data's `premises` command, meaning "occurs in an explicit
argument position of the ELABORATED TERM". propext, Eq.mpr and of_eq_true all
carry explicit in-edges in the tens of thousands and are typed by nobody.
Source-visible extraction therefore cannot recover the explicit set in full,
by construction — see extract.audit and split_hub_layers below.
"""

from __future__ import annotations

import json
import logging

import networkx as nx
import pandas as pd

from src import config

log = logging.getLogger(__name__)

_EXPLICIT_CACHE = config.MATHLIB_GRAPH_DIR / "_cache_explicit_edges.parquet"

# Node attributes carried onto the graph. split_hub_layers needs the first
# four; the rest support audit sampling and length control.
_NODE_ATTRS = (
    "kind", "file_module", "is_instance", "is_coercion",
    "module", "is_tactic_proof", "tactic_count", "in_degree", "dag_layer",
)


def _read_bool(series: pd.Series) -> pd.Series:
    """The CSVs store booleans as the strings 'True'/'False'."""
    if series.dtype == bool:
        return series
    return series.astype(str).str.strip().eq("True")


def load_node_frame() -> pd.DataFrame:
    """Declaration metadata, indexed by declaration name.

    Read from v2/declaration/metrics.csv rather than nodes.csv: identical row
    set, but it carries file_module / is_instance / is_coercion, which the
    layer partition depends on.
    """
    df = pd.read_csv(
        config.DECL_METRICS_CSV,
        usecols=["name", *_NODE_ATTRS],
        dtype={"name": str, "kind": str, "file_module": str, "module": str},
        keep_default_na=False,
        na_values=[],
    )
    # usecols returns columns in FILE order, not the order requested. _build
    # zips positionally against _NODE_ATTRS, so reorder explicitly or every
    # node attribute silently shifts by one column.
    df = df[["name", *_NODE_ATTRS]]
    for col in ("is_instance", "is_coercion", "is_tactic_proof"):
        df[col] = _read_bool(df[col])
    for col in ("tactic_count", "in_degree", "dag_layer"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(-1).astype(int)

    if len(df) != config.EXPECTED_DECL_NODES:
        raise ValueError(
            f"{config.DECL_METRICS_CSV.name} has {len(df):,} rows, expected "
            f"{config.EXPECTED_DECL_NODES:,}. Wrong file or wrong revision."
        )
    return df.set_index("name")


def load_edge_frame() -> pd.DataFrame:
    """All declaration edges, with the is_explicit flag.

    Reads mathlib_edges.csv — the mathlib-scoped graph. The repo also ships a
    root edges.csv with an identical header covering the full Lean environment
    (10.9M edges, 633,364 nodes); loading that one silently changes every
    number in the paper. config names only the correct path.
    """
    df = pd.read_csv(
        config.DECL_EDGES_CSV,
        usecols=["source", "target", "is_explicit"],
        dtype={"source": str, "target": str},
        keep_default_na=False,
        na_values=[],
    )
    df["is_explicit"] = _read_bool(df["is_explicit"])

    if len(df) != config.EXPECTED_DECL_EDGES:
        raise ValueError(
            f"{config.DECL_EDGES_CSV.name} has {len(df):,} rows, expected "
            f"{config.EXPECTED_DECL_EDGES:,}. Wrong file or wrong revision."
        )
    n_explicit = int(df["is_explicit"].sum())
    if n_explicit != config.EXPECTED_EXPLICIT_EDGES:
        raise ValueError(
            f"{n_explicit:,} explicit edges, expected "
            f"{config.EXPECTED_EXPLICIT_EDGES:,} (v2/summary.json)."
        )
    return df


def _report_dangling(edges: pd.DataFrame, names: set[str]) -> None:
    """Count edges whose endpoints are absent from the declaration list.

    The authors' own summary.md reports 15,914 missing sources and 12,885
    missing targets for their 633K-node extraction. Whether the mathlib-scoped
    files share that defect is measured here, never assumed.
    """
    missing_src = ~edges["source"].isin(names)
    missing_tgt = ~edges["target"].isin(names)
    n_src, n_tgt = int(missing_src.sum()), int(missing_tgt.sum())
    if n_src or n_tgt:
        log.warning(
            "dangling edges: %d with unknown source, %d with unknown target "
            "(of %d). Endpoints are added as attribute-less nodes.",
            n_src, n_tgt, len(edges),
        )


def _build(edges: pd.DataFrame, nodes: pd.DataFrame) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(
        (name, {a: row[i] for i, a in enumerate(_NODE_ATTRS)})
        for name, *row in nodes.itertuples(name=None)
    )
    _report_dangling(edges, set(g.nodes))
    g.add_edges_from(
        zip(edges["source"], edges["target"],
            ({"is_explicit": bool(e)} for e in edges["is_explicit"]))
    )
    return g


def load_declaration_graph() -> nx.DiGraph:
    """Full declaration graph, all edges (explicit + synthesized).

    Heavy: 8.4M edges is several GB of networkx adjacency. Analysis code
    wanting the object of study should call load_explicit_graph() instead,
    which never materialises this. This exists for whole-graph comparisons
    and for the audit's guard test.
    """
    return _build(load_edge_frame(), load_node_frame())


def explicit_subgraph(g: nx.DiGraph) -> nx.DiGraph:
    """Edges visible in source. THIS is the object of study, not the full graph."""
    keep = [(u, v) for u, v, e in g.edges(data=True) if e["is_explicit"]]
    sub = nx.DiGraph()
    sub.add_nodes_from(g.nodes(data=True))
    sub.add_edges_from(keep, is_explicit=True)
    return sub


def load_explicit_graph() -> nx.DiGraph:
    """The explicit subgraph, built without materialising the full graph.

    Equivalent to explicit_subgraph(load_declaration_graph()) — asserted in
    tests — but reads ~2.2M edges instead of 8.4M. Cached to parquet on first
    call; the cache lives under data/, which is gitignored.
    """
    if _EXPLICIT_CACHE.exists():
        edges = pd.read_parquet(_EXPLICIT_CACHE)
    else:
        edges = load_edge_frame()
        edges = edges[edges["is_explicit"]].reset_index(drop=True)
        edges.to_parquet(_EXPLICIT_CACHE, index=False)
    return _build(edges, load_node_frame())


def declaration_names(g: nx.DiGraph) -> set[str]:
    """Resolution target for premise extraction. Needed before E2 can start."""
    return set(g.nodes)


def is_language_infrastructure(attrs: dict) -> bool:
    """The four provenance rules. See split_hub_layers for why, not prefixes."""
    file_module = attrs.get("file_module") or ""
    return (
        not file_module.startswith(config.MATHLIB_MODULE_PREFIX)
        or bool(attrs.get("is_instance"))
        or bool(attrs.get("is_coercion"))
        or attrs.get("kind") in config.KERNEL_KINDS
    )


def split_hub_layers(g: nx.DiGraph) -> tuple[set[str], set[str]]:
    """Partition into (language infrastructure, mathematical content).

    Required before reporting any centrality number (CLAUDE.md §4), and it
    also fixes the audit's gate denominator — so it is frozen under §6.

    Prefix matching is NOT the mechanism. INFRASTRUCTURE_NAMESPACE_PREFIXES
    misses every root-level elaborator-inserted constant, and `kind` does not
    rescue it either: of_eq_true (in-degree 48,801) and funext (15,574) are
    both `theorem`. The reliable signal is provenance — every Lean-core
    constant has an empty file_module:

      1. file_module not under Mathlib.  -> Lean core / Init / Batteries
      2. is_instance or is_coercion      -> typeclass and coercion plumbing
      3. kind in KERNEL_KINDS            -> axiom/constructor/recursor/quotient
      4. generated-name markers          -> ._proof_, .injEq, .casesOn, ...

    Note this is language infrastructure vs mathematical CONTENT. The source
    paper's "mathematical infrastructure" hubs (CategoryTheory.Category, Real,
    TopologicalSpace, and structure classes like AddSemigroup) land on the
    mathematical side, which is what H2 needs.
    """
    infrastructure: set[str] = set()
    mathematical: set[str] = set()
    for name, attrs in g.nodes(data=True):
        if is_language_infrastructure(attrs) or any(
            m in name for m in config.GENERATED_NAME_MARKERS
        ):
            infrastructure.add(name)
        else:
            mathematical.add(name)

    _cross_check_prefixes(infrastructure, mathematical)
    return infrastructure, mathematical


def _cross_check_prefixes(infrastructure: set[str], mathematical: set[str]) -> None:
    """INFRASTRUCTURE_NAMESPACE_PREFIXES is retained only as a cross-check.

    The provenance partition should be a strict superset of what prefixes
    catch. Anything the prefixes call infrastructure but provenance does not
    is logged rather than silently reclassified — do not reintroduce prefix
    matching as the classifier.
    """
    def prefixed(name: str) -> bool:
        return any(
            name == p or name.startswith(p if p.endswith(".") else p + ".")
            for p in config.INFRASTRUCTURE_NAMESPACE_PREFIXES
        )

    divergent = {n for n in mathematical if prefixed(n)}
    if divergent:
        log.warning(
            "%d declarations match INFRASTRUCTURE_NAMESPACE_PREFIXES but are "
            "classified mathematical by provenance, e.g. %s",
            len(divergent), sorted(divergent)[:10],
        )


def load_tactic_usage() -> dict[str, list[str]]:
    """Per-declaration tactic lists from tactic_usage.ndjson.

    metrics.csv carries only tactic_count and top_tactic; the full list is
    needed to classify a proof as automation-bearing.
    """
    usage: dict[str, list[str]] = {}
    with open(config.TACTIC_USAGE_NDJSON, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            name = rec.get("name")
            if name is not None:
                usage[name] = rec.get("tactics") or []
    return usage


def automation_stratum(tactics: list[str]) -> str:
    """'automation' if any goal-closing automation tactic is used, else 'none'.

    The distinction matters because automation closes goals without naming the
    premises it uses, so those premises are invisible to source extraction.
    This is a stratification, never an exclusion (CLAUDE.md §6).
    """
    return (
        "automation"
        if any(t in config.AUTOMATION_TACTICS for t in tactics)
        else "none"
    )


def graph_summary() -> dict:
    """The publishers' own counts, for asserting against at load time."""
    with open(config.GRAPH_SUMMARY_JSON) as f:
        return json.load(f)
