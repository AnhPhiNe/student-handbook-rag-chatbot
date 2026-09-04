import os
import json
import logging
from typing import List, Dict, Any
import networkx as nx

logger = logging.getLogger("graph_traverser")


class NetworkXGraphTraverser:
    """Expand retrieved seeds through typed document-reference edges."""

    def __init__(self, edges_file: str = "data/processed/graphs/document_edges.json"):
        """Load the directed multi-graph into memory for traversal."""
        self.edges_file = edges_file
        self.graph = (
            nx.MultiDiGraph()
        )  # Preserve distinct edges between the same nodes.
        self._load_graph()

    def _load_graph(self):
        if not os.path.exists(self.edges_file):
            logger.warning(f"Không tìm thấy file {self.edges_file}. Đồ thị sẽ trống.")
            return

        with open(self.edges_file, "r", encoding="utf-8") as f:
            edges = json.load(f)

        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            relation = edge.get("relation", "LIEN_QUAN_TOI")
            reason = edge.get("reason", "")

            if source and target:
                self.graph.add_edge(source, target, relation=relation, reason=reason)

        logger.info(
            f"Đã nạp NetworkX Đồ thị: {self.graph.number_of_nodes()} Nodes, {self.graph.number_of_edges()} Edges."
        )

    def expand_context(
        self, seed_ids: List[str], max_depth: int = 2
    ) -> List[Dict[str, Any]]:
        """Expand multiple seeds with BFS while preserving nearest-seed ownership."""
        from collections import deque

        expanded_nodes = []
        # Map each visited node to its shortest depth and originating seed.
        visited: Dict[str, tuple] = {}

        # Frontier items contain node, originating seed, depth, and direct parent.
        frontier = deque(
            [(seed, seed, 0, None) for seed in seed_ids if seed in self.graph]
        )

        while frontier:
            node, origin_seed, depth, parent_node = frontier.popleft()

            # Layered BFS guarantees the first visit is through a shortest path.
            # This invariant also makes nearest-seed ownership deterministic.
            if node in visited:
                continue

            visited[node] = (depth, origin_seed)

            # Emit only expanded nodes, not the original depth-zero seeds.
            if depth > 0:
                reason = ""
                if parent_node:
                    edge_data = self.graph.get_edge_data(parent_node, node)
                    if edge_data:
                        # Use the first edge when parallel graph edges exist.
                        reason = edge_data[0].get("reason", "")

                expanded_nodes.append(
                    {
                        "id": node,
                        "depth": depth,
                        "seed_source": origin_seed,
                        "reason": reason,
                    }
                )

            # Expand neighbors only before the configured depth boundary.
            if depth < max_depth:
                # Visit direct successors from the current node.
                for neighbor in self.graph.successors(node):
                    if neighbor not in visited:
                        frontier.append((neighbor, origin_seed, depth + 1, node))

        return expanded_nodes
