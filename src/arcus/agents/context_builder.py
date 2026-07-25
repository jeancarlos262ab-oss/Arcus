"""Context Builder Agent: Enriches envelope with code graph context for PR analysis."""
import logging
from typing import Any

from arcus.agents.base import agent_handler, mark_section_failed, mark_section_ok
from arcus.contracts import ContextConventions, PipelineEnvelope
from arcus.graph import extract_subgraph

logger = logging.getLogger(__name__)


@agent_handler
def handle_context_builder(envelope: PipelineEnvelope) -> PipelineEnvelope:
    """
    Context Builder Agent Handler.

    Builds or queries the code graph for the PR's changed files and enriches
    the envelope with context (conventions, graph references, subgraph).

    This is the first analysis agent in the pipeline. It populates the
    `envelope.context` section with:
    - status: 'ok' or 'failed'
    - graph_ref: S3 reference to full graph (if available)
    - graph_version: Commit SHA of graph
    - relevant_subgraph_ref: S3 reference to subgraph for changed files
    - conventions: Detected/configured code conventions
    - error: If something failed

    Args:
        envelope: Pipeline envelope with PR details.

    Returns:
        Updated envelope with context section populated.
    """
    try:
        # Step 1: Extract PR metadata
        pr = envelope.pr
        logger.info(
            f"Building context for PR: {pr.repo_full_name}#{pr.pr_number} (commit {pr.commit_sha[:8]})"
        )
        logger.info(f"Changed files: {pr.changed_files}")

        # Step 2: Build or load graph (simulated - in production would use S3)
        # For MVP, we build from fixtures and extract subgraph
        try:
            graph = _build_or_load_graph(pr)
        except Exception as graph_error:
            logger.warning(
                f"Failed to build graph: {type(graph_error).__name__}: {graph_error}"
            )
            # Fall back to empty graph mode (diff-only)
            graph = None

        # Step 3: Extract subgraph for changed files
        if graph is not None and pr.changed_files:
            try:
                subgraph = extract_subgraph(graph, pr.changed_files, hops=1)
                logger.info(
                    f"Extracted subgraph: {len(subgraph.nodes)} nodes, {len(subgraph.edges)} edges"
                )
            except Exception as subgraph_error:
                logger.warning(
                    f"Failed to extract subgraph: {type(subgraph_error).__name__}: {subgraph_error}"
                )
                subgraph = None
        else:
            subgraph = None

        # Step 4: Detect conventions from code (heuristic)
        conventions = _detect_conventions(graph, subgraph)

        # Step 5: Populate context section
        envelope.context.status = "ok"
        envelope.context.graph_version = pr.commit_sha
        envelope.context.conventions = conventions

        # In production, graph_ref and relevant_subgraph_ref would be S3 URLs
        if graph is not None:
            envelope.context.graph_ref = f"s3://arcus-graphs/{pr.repo_full_name}/main.json"

        if subgraph is not None:
            envelope.context.relevant_subgraph_ref = (
                f"s3://arcus-graphs/{pr.repo_full_name}/pr-{pr.pr_number}/subgraph.json"
            )

        envelope.context.error = None
        mark_section_ok(envelope, "context")

        logger.info("Context Builder: Successfully enriched envelope")
        return envelope

    except Exception as error:
        logger.error(
            f"Context Builder failed: {type(error).__name__}: {error}",
            exc_info=True,
        )
        mark_section_failed(
            envelope,
            "context",
            "CONTEXT_BUILDER_ERROR",
            str(error),
        )
        return envelope


def _build_or_load_graph(pr: Any) -> Any:
    """
    Build or load graph for the repository.

    In production, this would:
    1. Check S3 for existing graph of main branch
    2. If not found, clone repo and build graph
    3. Cache in S3

    For MVP/testing, returns a mock graph.

    Args:
        pr: PR details with repo information.

    Returns:
        RepoGraph instance or None if unavailable.
    """
    # MVP: Return None (graph would be built by Frente D in setup)
    # In production:
    # - Try to load from S3: s3://arcus-graphs/{repo_full_name}/main.json
    # - If not found, build from repository and cache
    # - Return cached RepoGraph

    # For now, simulate having a graph available but empty
    from arcus.contracts import RepoGraph

    logger.debug("Mock: Loading graph for PR context (MVP returns empty graph)")
    return RepoGraph(nodes=[], edges=[])


def _detect_conventions(graph: Any, subgraph: Any) -> ContextConventions:
    """
    Detect code conventions from the graph.

    Heuristics:
    - Naming: Look at function/class names (snake_case, camelCase, etc.)
    - Error handling: Look for common patterns (try/except, custom exceptions)
    - Module structure: Check for `__init__.py`, package patterns

    Args:
        graph: Full RepoGraph or None.
        subgraph: Subgraph for changed files or None.

    Returns:
        ContextConventions with detected conventions.
    """
    # MVP: Return default conventions
    # In production, analyze the graph and detect patterns

    conventions = ContextConventions(
        naming="snake_case",  # Default for Python
        error_handling="custom exceptions",  # Common Python pattern
        notes=[],
    )

    # Detect from subgraph if available
    if subgraph is not None:
        try:
            # Heuristic: Check node names for naming convention
            names = [node.name for node in subgraph.nodes if node.type in ("function", "class")]

            if names:
                # Simple heuristic: if most have underscores, snake_case
                snake_case_count = sum(1 for n in names if "_" in n)
                if snake_case_count / len(names) > 0.5:
                    conventions.naming = "snake_case"
                else:
                    conventions.naming = "mixed"

                conventions.notes.append(f"Analyzed {len(names)} definitions")
        except Exception as error:
            logger.debug(f"Convention detection heuristic failed: {error}")

    return conventions
