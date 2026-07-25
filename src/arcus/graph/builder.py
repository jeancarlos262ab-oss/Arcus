"""Graph builder: Parse Python files and build code structure graph using tree-sitter."""
import hashlib
from pathlib import Path
from typing import Any

import networkx as nx
from tree_sitter import Language, Parser
from tree_sitter_python import language as get_python_language

from arcus.contracts import Edge, Node, RepoGraph

# Get the tree-sitter Python language
PYTHON_LANGUAGE = Language(get_python_language())


class GraphBuilder:
    """
    Build a RepoGraph from Python source files using tree-sitter AST parsing.

    Extracts:
    - Nodes: modules, classes, functions
    - Edges: imports, function calls, class definitions
    """

    def __init__(self) -> None:
        """Initialize the graph builder with tree-sitter parser."""
        self.parser = Parser()
        self.parser.language = PYTHON_LANGUAGE
        self.graph = nx.DiGraph()
        self.nodes_list: list[Node] = []
        self.edges_list: list[Edge] = []

    def parse_file(self, file_path: Path) -> RepoGraph:
        """
        Parse a single Python file and return a RepoGraph.

        Args:
            file_path: Path to the Python file to parse.

        Returns:
            A RepoGraph containing nodes and edges extracted from the file.

        Raises:
            IOError: If the file cannot be read.
        """
        with open(file_path, "rb") as f:
            source_code = f.read()

        tree = self.parser.parse(source_code)
        root = tree.root_node

        # Create file node
        file_id = self._make_id("file", str(file_path))
        file_node = Node(
            id=file_id,
            type="file",
            file=str(file_path),
            name=file_path.name,
            metadata={"lines": self._count_lines(source_code)},
        )
        self.nodes_list.append(file_node)

        # Extract top-level definitions
        self._extract_definitions(root, file_path, file_id, source_code)

        return RepoGraph(nodes=self.nodes_list, edges=self.edges_list)

    def parse_directory(self, dir_path: Path) -> RepoGraph:
        """
        Parse all Python files in a directory recursively.

        Args:
            dir_path: Directory path to scan for Python files.

        Returns:
            A RepoGraph combining all nodes and edges from the directory.
        """
        python_files = list(dir_path.rglob("*.py"))

        for file_path in python_files:
            try:
                self.parse_file(file_path)
            except (OSError, Exception) as e:
                # Log error but continue processing other files
                print(f"Warning: Failed to parse {file_path}: {e}")

        return RepoGraph(nodes=self.nodes_list, edges=self.edges_list)

    def _extract_definitions(
        self, node: Any, file_path: Path, file_id: str, source_code: bytes, is_in_class: bool = False
    ) -> None:
        """
        Extract function, class, and import definitions from AST node.

        Args:
            node: Tree-sitter node to process.
            file_path: Path to the file being parsed.
            file_id: ID of the file node.
            source_code: Source code bytes for line extraction.
            is_in_class: Whether we're currently inside a class definition.
        """
        if node.type == "function_definition" and not is_in_class:
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = name_node.text.decode()
                func_id = self._make_id("func", str(file_path), func_name)
                func_node = Node(
                    id=func_id,
                    type="function",
                    file=str(file_path),
                    name=func_name,
                    metadata={
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "is_public": not func_name.startswith("_"),
                    },
                )
                self.nodes_list.append(func_node)
                # Add edge: file contains function
                self.edges_list.append(
                    Edge(source=file_id, target=func_id, type="contains")
                )

        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                class_name = name_node.text.decode()
                class_id = self._make_id("class", str(file_path), class_name)
                class_node = Node(
                    id=class_id,
                    type="class",
                    file=str(file_path),
                    name=class_name,
                    metadata={
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                    },
                )
                self.nodes_list.append(class_node)
                # Add edge: file contains class
                self.edges_list.append(
                    Edge(source=file_id, target=class_id, type="contains")
                )

                # Extract methods from class (methods are in the class's block)
                for child in node.children:
                    if child.type == "block":
                        # Methods are function_definitions inside the class block
                        for block_child in child.children:
                            if block_child.type in ("function_definition", "decorated_definition"):
                                func_def = block_child
                                if block_child.type == "decorated_definition":
                                    # Find the function_definition within the decoration
                                    for sub_child in block_child.children:
                                        if sub_child.type == "function_definition":
                                            func_def = sub_child
                                            break

                                if func_def.type == "function_definition":
                                    method_name_node = func_def.child_by_field_name("name")
                                    if method_name_node:
                                        method_name = method_name_node.text.decode()
                                        method_id = self._make_id(
                                            "method", str(file_path), class_name, method_name
                                        )
                                        method_node = Node(
                                            id=method_id,
                                            type="method",
                                            file=str(file_path),
                                            name=method_name,
                                            metadata={
                                                "line_start": func_def.start_point[0] + 1,
                                                "line_end": func_def.end_point[0] + 1,
                                                "is_method": True,
                                            },
                                        )
                                        self.nodes_list.append(method_node)
                                        # Add edge: class contains method
                                        self.edges_list.append(
                                            Edge(source=class_id, target=method_id, type="contains")
                                        )
                        # Return early to avoid recursive processing
                        return

        elif node.type == "import_statement":
            # Extract import statements
            self._extract_imports(node, file_id)

        elif node.type == "import_from_statement":
            # Extract from...import statements
            self._extract_from_imports(node, file_id)

        # Recursively process children
        for child in node.children:
            self._extract_definitions(child, file_path, file_id, source_code, is_in_class)

    def _extract_imports(self, node: Any, file_id: str) -> None:
        """
        Extract import statements and create edges.

        Args:
            node: Tree-sitter import_statement node.
            file_id: ID of the file containing the import.
        """
        for child in node.children:
            if child.type == "dotted_name":
                module_name = child.text.decode()
                # Create edge: file imports module
                self.edges_list.append(
                    Edge(source=file_id, target=module_name, type="imports")
                )

    def _extract_from_imports(self, node: Any, file_id: str) -> None:
        """
        Extract from...import statements and create edges.

        Args:
            node: Tree-sitter import_from_statement node.
            file_id: ID of the file containing the import.
        """
        module_name = None
        for child in node.children:
            if child.type == "dotted_name":
                module_name = child.text.decode()
            elif child.type == "import_alias":
                # Handle: from module import name
                pass

        if module_name:
            self.edges_list.append(
                Edge(source=file_id, target=module_name, type="imports_from")
            )

    def _make_id(self, *parts: str) -> str:
        """
        Generate a unique ID for a node.

        Args:
            *parts: Components to hash (type, file, name, etc.).

        Returns:
            A hash-based ID string.
        """
        combined = ":".join(str(p) for p in parts)
        return f"{parts[0][:3]}_{hashlib.md5(combined.encode()).hexdigest()[:9]}"

    @staticmethod
    def _count_lines(source_code: bytes) -> int:
        """Count lines in source code."""
        return len(source_code.split(b"\n"))

    def reset(self) -> None:
        """Reset the builder state for a new parse operation."""
        self.graph = nx.DiGraph()
        self.nodes_list = []
        self.edges_list = []


def update_graph_incremental(
    existing_graph: RepoGraph,
    modified_files: list[str],
    deleted_files: list[str] | None = None,
) -> RepoGraph:
    """
    Incrementally update a RepoGraph with changes from modified/deleted files.

    Only re-parses modified files instead of the entire codebase.
    Removes nodes and edges associated with deleted files.

    Args:
        existing_graph: The previous RepoGraph to update.
        modified_files: List of file paths that were modified.
        deleted_files: Optional list of file paths that were deleted.

    Returns:
        Updated RepoGraph with changes applied.
    """
    if deleted_files is None:
        deleted_files = []

    # Convert existing graph to mutable form
    updated_nodes = list(existing_graph.nodes) if existing_graph.nodes else []
    updated_edges = list(existing_graph.edges) if existing_graph.edges else []

    # Build set of file IDs for efficient lookup
    builder = GraphBuilder()
    deleted_file_ids = set()
    for deleted_file in deleted_files:
        deleted_file_id = builder._make_id("file", deleted_file)
        deleted_file_ids.add(deleted_file_id)

    # Step 1: Remove nodes and edges related to deleted files
    nodes_to_remove = {
        node.id for node in updated_nodes if node.file in deleted_files
    }
    nodes_to_remove.update(deleted_file_ids)

    updated_nodes = [node for node in updated_nodes if node.id not in nodes_to_remove]
    updated_edges = [
        edge
        for edge in updated_edges
        if edge.source not in nodes_to_remove and edge.target not in nodes_to_remove
    ]

    # Step 2: Re-parse modified files and extract new nodes/edges
    for modified_file in modified_files:
        file_path = Path(modified_file)

        # Remove old nodes/edges for this file
        old_file_id = builder._make_id("file", modified_file)
        old_nodes_for_file = {
            node.id for node in updated_nodes if node.file == modified_file
        }
        old_nodes_for_file.add(old_file_id)

        updated_nodes = [
            node for node in updated_nodes if node.id not in old_nodes_for_file
        ]
        updated_edges = [
            edge
            for edge in updated_edges
            if edge.source not in old_nodes_for_file
            and edge.target not in old_nodes_for_file
        ]

        # Parse the modified file
        if file_path.exists():
            try:
                builder.reset()
                new_graph = builder.parse_file(file_path)

                # Add new nodes and edges
                if new_graph.nodes:
                    updated_nodes.extend(new_graph.nodes)
                if new_graph.edges:
                    updated_edges.extend(new_graph.edges)

            except (OSError, Exception) as e:
                # Log error but continue processing other files
                print(f"Warning: Failed to re-parse {modified_file}: {e}")
                # If parse fails, keep the old version
                for node in existing_graph.nodes or []:
                    if node.file == modified_file and node.id not in old_nodes_for_file:
                        updated_nodes.append(node)
                for edge in existing_graph.edges or []:
                    if (
                        edge.source not in old_nodes_for_file
                        and edge.target not in old_nodes_for_file
                    ):
                        updated_edges.append(edge)

    return RepoGraph(nodes=updated_nodes, edges=updated_edges)
