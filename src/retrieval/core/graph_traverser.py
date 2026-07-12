import os
import json
import logging
from typing import List, Dict, Any, Set
import networkx as nx

logger = logging.getLogger("graph_traverser")

class NetworkXGraphTraverser:
    def __init__(self, edges_file: str = "data/processed/graphs/document_edges.json"):
        """
        Khởi tạo và Load Đồ thị vào RAM (In-memory)
        """
        self.edges_file = edges_file
        self.graph = nx.MultiDiGraph() # Đồ thị có hướng, cho phép đa cạnh
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
                
        logger.info(f"Đã nạp NetworkX Đồ thị: {self.graph.number_of_nodes()} Nodes, {self.graph.number_of_edges()} Edges.")

    def expand_context(self, seed_ids: List[str], max_depth: int = 2) -> List[Dict[str, Any]]:
        """
        Duyệt BFS Đa nguồn (Multi-source BFS) từ tất cả seed_ids cùng lúc.
        Đảm bảo mỗi node luôn được gán cho độ sâu ngắn nhất (Graph Proximity) 
        và thuộc về seed gốc gần nó nhất thực sự.
        """
        from collections import deque
        
        expanded_nodes = []
        # visited map lưu: node_id -> (depth, origin_seed)
        visited: Dict[str, tuple] = {}
        
        # frontier chứa tuple: (current_node, origin_seed, depth, direct_parent)
        frontier = deque([(seed, seed, 0, None) for seed in seed_ids if seed in self.graph])
        
        while frontier:
            node, origin_seed, depth, parent_node = frontier.popleft()
            
            # BFS chạy theo tầng (depth=0 -> depth=1 -> depth=2).
            # Do đó, lần ĐẦU TIÊN ta pop được một node, đó TẤT YẾU là đường đi ngắn nhất tới nó.
            if node in visited:
                continue
                
            visited[node] = (depth, origin_seed)
            
            # Nếu node này không phải là seed ban đầu (depth > 0), ta thêm vào kết quả
            if depth > 0:
                reason = ""
                if parent_node:
                    edge_data = self.graph.get_edge_data(parent_node, node)
                    if edge_data:
                        # Với MultiDiGraph, lấy cạnh index 0
                        reason = edge_data[0].get("reason", "")
                
                expanded_nodes.append({
                    "id": node,
                    "depth": depth,
                    "seed_source": origin_seed,
                    "reason": reason
                })
                
            # Tiếp tục bung lụa nếu chưa chạm giới hạn độ sâu
            if depth < max_depth:
                # Tìm các láng giềng trực tiếp
                for neighbor in self.graph.successors(node):
                    if neighbor not in visited:
                        frontier.append((neighbor, origin_seed, depth + 1, node))
                        
        return expanded_nodes
