"""Tree-sitter builder for the canonical repository graph."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from tree_sitter import Language, Parser
from tree_sitter import Node as SyntaxNode
from tree_sitter_python import language as get_python_language

from arcus.contracts import (
    ContextConventions,
    GraphEdgeType,
    GraphLink,
    GraphNode,
    GraphNodeKind,
    RepoGraph,
)

PYTHON_LANGUAGE = Language(get_python_language())


class GraphBuilder:
    """Build a deterministic Python source graph using tree-sitter."""

    def __init__(
        self,
        repo: str,
        graph_version: str,
        *,
        root_path: Path | None = None,
        built_at: datetime | None = None,
    ) -> None:
        """Configure repository metadata attached to every produced graph."""

        self._repo = repo
        self._graph_version = graph_version
        self._root_path = (root_path or Path.cwd()).resolve()
        self._built_at = built_at or datetime.now(UTC)
        self._parser = Parser(PYTHON_LANGUAGE)
        self._nodes: list[GraphNode] = []
        self._links: list[GraphLink] = []
        self._syntax_trees: list[tuple[str, ast.Module]] = []

    def parse_file(self, file_path: Path) -> RepoGraph:
        """Parse one Python file into a standalone repository graph."""

        self.reset()
        self._parse_file_into_graph(file_path)
        self._extract_semantic_links()
        return self._graph()

    def parse_directory(self, directory: Path) -> RepoGraph:
        """Parse Python files and connect cross-file semantic relationships."""

        self.reset()
        for file_path in sorted(directory.rglob("*.py")):
            self._parse_file_into_graph(file_path)
        self._extract_semantic_links()
        return self._graph()

    def reset(self) -> None:
        """Clear accumulated nodes and links before a new build."""

        self._nodes = []
        self._links = []
        self._syntax_trees = []

    def _parse_file_into_graph(self, file_path: Path) -> None:
        """Append one file and its top-level definitions to the current graph."""

        source = file_path.read_bytes()
        relative_path = self._relative_path(file_path)
        root = self._parser.parse(source).root_node
        python_tree = ast.parse(source.decode("utf-8"), filename=relative_path)
        self._syntax_trees.append((relative_path, python_tree))
        line_end = max(1, len(source.splitlines()))
        module_id = relative_path
        self._nodes.append(
            GraphNode(
                id=module_id,
                kind=GraphNodeKind.MODULE,
                file=relative_path,
                name=file_path.stem,
                line_start=1,
                line_end=line_end,
                docstring_present=_has_docstring(root, source),
            )
        )
        self._extract_definitions(root, source, relative_path, module_id)

    def _extract_definitions(
        self,
        node: SyntaxNode,
        source: bytes,
        relative_path: str,
        parent_id: str,
    ) -> None:
        """Append functions/classes directly contained by an AST node."""

        body = node.child_by_field_name("body")
        children = body.named_children if body is not None else node.named_children
        for child in children:
            definition = _unwrap_decorated(child)
            if definition.type == "function_definition":
                self._append_definition(
                    definition,
                    source,
                    relative_path,
                    parent_id,
                    GraphNodeKind.METHOD
                    if parent_id != relative_path
                    else GraphNodeKind.FUNCTION,
                )
            elif definition.type == "class_definition":
                class_id = self._append_definition(
                    definition,
                    source,
                    relative_path,
                    parent_id,
                    GraphNodeKind.CLASS,
                )
                self._extract_definitions(
                    definition,
                    source,
                    relative_path,
                    class_id,
                )

    def _append_definition(
        self,
        node: SyntaxNode,
        source: bytes,
        relative_path: str,
        parent_id: str,
        kind: GraphNodeKind,
    ) -> str:
        """Append one definition node and its parent ``defines`` link."""

        name_node = node.child_by_field_name("name")
        if name_node is None:
            raise ValueError("definition is missing a name")
        name = _text(name_node, source)
        node_id = f"{parent_id}::{name}"
        self._nodes.append(
            GraphNode(
                id=node_id,
                kind=kind,
                file=relative_path,
                name=name,
                line_start=node.start_point.row + 1,
                line_end=node.end_point.row + 1,
                signature=_signature(node, source),
                docstring_present=_has_docstring(node, source),
            )
        )
        self._links.append(
            GraphLink(
                source=parent_id,
                target=node_id,
                type=GraphEdgeType.DEFINES,
            )
        )
        return node_id

    def _extract_semantic_links(self) -> None:
        """Resolve repository-local imports, calls, and inheritance relationships."""

        node_ids = {node.id for node in self._nodes}
        nodes_by_name: dict[str, list[GraphNode]] = defaultdict(list)
        nodes_by_file_name: dict[tuple[str, str], list[GraphNode]] = defaultdict(list)
        module_files: dict[str, str] = {}
        for node in self._nodes:
            nodes_by_name[node.name].append(node)
            nodes_by_file_name[(node.file, node.name)].append(node)
            if node.kind is GraphNodeKind.MODULE:
                module_files[_module_name(node.file)] = node.file

        link_keys = {(link.source, link.target, link.type) for link in self._links}

        def append_link(source: str, target: str, edge_type: GraphEdgeType) -> None:
            key = (source, target, edge_type)
            if source not in node_ids or target not in node_ids or key in link_keys:
                return
            self._links.append(GraphLink(source=source, target=target, type=edge_type))
            link_keys.add(key)

        for file_path, syntax_tree in self._syntax_trees:
            imported_nodes, imported_modules = _collect_imports(
                syntax_tree,
                file_path,
                module_files,
                nodes_by_file_name,
                append_link,
            )
            visitor = _RelationshipVisitor(
                file_path=file_path,
                node_ids=node_ids,
                nodes_by_name=nodes_by_name,
                nodes_by_file_name=nodes_by_file_name,
                imported_nodes=imported_nodes,
                imported_modules=imported_modules,
                append_link=append_link,
            )
            visitor.visit(syntax_tree)

    def _relative_path(self, file_path: Path) -> str:
        """Return a stable POSIX path relative to the configured repository root."""

        resolved = file_path.resolve()
        try:
            relative = resolved.relative_to(self._root_path)
        except ValueError:
            relative = Path(file_path.name)
        return relative.as_posix()

    def _graph(self) -> RepoGraph:
        """Build the validated graph from accumulated entities."""

        return RepoGraph(
            repo=self._repo,
            graph_version=self._graph_version,
            built_at=self._built_at,
            conventions=ContextConventions(),
            nodes=self._nodes,
            links=self._links,
        )


class _RelationshipVisitor(ast.NodeVisitor):
    """Emit calls and inheritance links while tracking the current definition."""

    def __init__(
        self,
        *,
        file_path: str,
        node_ids: set[str],
        nodes_by_name: dict[str, list[GraphNode]],
        nodes_by_file_name: dict[tuple[str, str], list[GraphNode]],
        imported_nodes: dict[str, GraphNode],
        imported_modules: dict[str, str],
        append_link: Callable[[str, str, GraphEdgeType], None],
    ) -> None:
        self._file_path = file_path
        self._node_ids = node_ids
        self._nodes_by_name = nodes_by_name
        self._nodes_by_file_name = nodes_by_file_name
        self._imported_nodes = imported_nodes
        self._imported_modules = imported_modules
        self._append_link = append_link
        self._owners = [file_path]
        self._classes: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class ownership and resolve direct repository base classes."""

        class_id = f"{self._owners[-1]}::{node.name}"
        if class_id not in self._node_ids:
            self.generic_visit(node)
            return
        for base in node.bases:
            target = self._resolve_expression(base)
            if target is not None:
                self._append_link(class_id, target.id, GraphEdgeType.INHERITS)
        self._owners.append(class_id)
        self._classes.append(class_id)
        self.generic_visit(node)
        self._classes.pop()
        self._owners.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function or method ownership for nested call expressions."""

        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async functions using the same graph identifier convention."""

        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Connect the current definition to an unambiguous call target."""

        target = self._resolve_expression(node.func)
        if target is not None:
            self._append_link(self._owners[-1], target.id, GraphEdgeType.CALLS)
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        owner_id = f"{self._owners[-1]}::{node.name}"
        if owner_id not in self._node_ids:
            self.generic_visit(node)
            return
        self._owners.append(owner_id)
        self.generic_visit(node)
        self._owners.pop()

    def _resolve_expression(self, expression: ast.expr) -> GraphNode | None:
        if isinstance(expression, ast.Name):
            imported = self._imported_nodes.get(expression.id)
            if imported is not None:
                return imported
            return _one(
                self._nodes_by_file_name.get((self._file_path, expression.id))
            ) or _one(self._nodes_by_name.get(expression.id))
        if not isinstance(expression, ast.Attribute):
            return None
        if isinstance(expression.value, ast.Name):
            if expression.value.id == "self" and self._classes:
                target_id = f"{self._classes[-1]}::{expression.attr}"
                return next(
                    (
                        node
                        for node in self._nodes_by_name.get(expression.attr, [])
                        if node.id == target_id
                    ),
                    None,
                )
            module_file = self._imported_modules.get(expression.value.id)
            if module_file is not None:
                return _one(
                    self._nodes_by_file_name.get((module_file, expression.attr))
                )
        return None


def _collect_imports(
    syntax_tree: ast.Module,
    file_path: str,
    module_files: dict[str, str],
    nodes_by_file_name: dict[tuple[str, str], list[GraphNode]],
    append_link: Callable[[str, str, GraphEdgeType], None],
) -> tuple[dict[str, GraphNode], dict[str, str]]:
    """Collect local import aliases and emit module-to-module import links."""

    imported_nodes: dict[str, GraphNode] = {}
    imported_modules: dict[str, str] = {}
    current_module = _module_name(file_path)
    for node in ast.walk(syntax_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target_file = module_files.get(alias.name)
                if target_file is None:
                    continue
                binding = alias.asname or alias.name.split(".")[0]
                imported_modules[binding] = target_file
                append_link(file_path, target_file, GraphEdgeType.IMPORTS)
        elif isinstance(node, ast.ImportFrom):
            module_name = _resolve_import_name(
                current_module,
                file_path,
                node.module,
                node.level,
            )
            target_file = module_files.get(module_name)
            for alias in node.names:
                if alias.name == "*":
                    continue
                alias_target_file = target_file or module_files.get(
                    f"{module_name}.{alias.name}".strip(".")
                )
                if alias_target_file is None:
                    continue
                append_link(file_path, alias_target_file, GraphEdgeType.IMPORTS)
                binding = alias.asname or alias.name
                target = _one(nodes_by_file_name.get((alias_target_file, alias.name)))
                if target is None:
                    imported_modules[binding] = alias_target_file
                else:
                    imported_nodes[binding] = target
    return imported_nodes, imported_modules


def _module_name(file_path: str) -> str:
    """Convert a repository-relative Python path to its importable module name."""

    path = Path(file_path)
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_import_name(
    current_module: str,
    file_path: str,
    imported_module: str | None,
    level: int,
) -> str:
    """Resolve an absolute module name for one ``from`` import."""

    if level == 0:
        return imported_module or ""
    current_parts = current_module.split(".") if current_module else []
    if Path(file_path).stem != "__init__" and current_parts:
        current_parts.pop()
    ascend = max(0, level - 1)
    if ascend:
        current_parts = current_parts[: max(0, len(current_parts) - ascend)]
    if imported_module:
        current_parts.extend(imported_module.split("."))
    return ".".join(current_parts)


def _one(nodes: list[GraphNode] | None) -> GraphNode | None:
    """Return the sole unambiguous graph node from a candidate collection."""

    return nodes[0] if nodes is not None and len(nodes) == 1 else None


def update_graph_incremental(
    existing_graph: RepoGraph,
    modified_files: list[str],
    deleted_files: list[str] | None = None,
    *,
    root_path: Path | None = None,
    graph_version: str | None = None,
) -> RepoGraph:
    """Replace entities for modified files and remove deleted-file entities."""

    removed_files = {
        path.replace("\\", "/") for path in [*modified_files, *(deleted_files or [])]
    }
    retained_nodes = [
        node for node in existing_graph.nodes if node.file not in removed_files
    ]
    retained_ids = {node.id for node in retained_nodes}
    retained_links = [
        link
        for link in existing_graph.links
        if link.source in retained_ids and link.target in retained_ids
    ]

    builder = GraphBuilder(
        existing_graph.repo,
        graph_version or existing_graph.graph_version,
        root_path=root_path,
    )
    new_nodes: list[GraphNode] = []
    new_links: list[GraphLink] = []
    for path_text in modified_files:
        path = Path(path_text)
        if not path.is_absolute() and root_path is not None:
            path = root_path / path
        if not path.exists() or path.suffix != ".py":
            continue
        parsed = builder.parse_file(path)
        new_nodes.extend(parsed.nodes)
        new_links.extend(parsed.links)

    return existing_graph.model_copy(
        update={
            "graph_version": graph_version or existing_graph.graph_version,
            "built_at": datetime.now(UTC),
            "nodes": [*retained_nodes, *new_nodes],
            "links": [*retained_links, *new_links],
        }
    )


def _unwrap_decorated(node: SyntaxNode) -> SyntaxNode:
    """Return the definition wrapped by a decorated-definition node."""

    if node.type != "decorated_definition":
        return node
    definition = node.child_by_field_name("definition")
    return definition or node


def _text(node: SyntaxNode, source: bytes) -> str:
    """Decode one syntax-node byte span as UTF-8."""

    return source[node.start_byte : node.end_byte].decode("utf-8")


def _signature(node: SyntaxNode, source: bytes) -> str | None:
    """Extract the definition header without its body."""

    body = node.child_by_field_name("body")
    end_byte = body.start_byte if body is not None else node.end_byte
    signature = source[node.start_byte : end_byte].decode("utf-8").rstrip().rstrip(":")
    return signature or None


def _has_docstring(node: SyntaxNode, source: bytes) -> bool:
    """Detect a leading string expression in a module or definition body."""

    body = node.child_by_field_name("body")
    children = body.named_children if body is not None else node.named_children
    if not children:
        return False
    first = children[0]
    if first.type != "expression_statement" or not first.named_children:
        return False
    return first.named_children[0].type in {"string", "concatenated_string"}
