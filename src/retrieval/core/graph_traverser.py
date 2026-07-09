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
        Từ danh sách ID (Hạt giống) ban đầu, lan truyền tìm láng giềng theo chiều rộng (BFS).
        Trả về danh sách các Node láng giềng kèm theo Đường dẫn (Path) và Lý do liên quan.
        """
        expanded_nodes = []
        visited_nodes: Set[str] = set(seed_ids) # Đánh dấu Seed là đã ghé thăm để tránh trả về chính Seed
        
        for seed_node in seed_ids:
            if seed_node not in self.graph:
                continue
                
            # Duyệt BFS từ seed_node, với giới hạn độ sâu (cutoff)
            # lengths trả về dict {node_id: khoảng_cách}
            lengths = nx.single_source_shortest_path_length(self.graph, seed_node, cutoff=max_depth)
            
            for neighbor_id, depth in lengths.items():
                if depth == 0 or neighbor_id in visited_nodes:
                    continue # Bỏ qua Node gốc hoặc Node đã có
                
                # Tìm lý do liên kết (Edge attribute) từ node cha đến node con
                # Để đơn giản, ta lấy cạnh ngắn nhất nối từ seed tới neighbor
                try:
                    path = nx.shortest_path(self.graph, source=seed_node, target=neighbor_id)
                    # Lấy lý do của bước cuối cùng trong path
                    direct_source = path[-2]
                    edge_data = self.graph.get_edge_data(direct_source, neighbor_id)
                    reason = edge_data[0].get("reason", "") if edge_data else ""
                except nx.NetworkXNoPath:
                    reason = "Liên kết mạng nhện chéo"
                
                expanded_nodes.append({
                    "id": neighbor_id,
                    "depth": depth,
                    "seed_source": seed_node,
                    "reason": reason
                })
                visited_nodes.add(neighbor_id)
                
        return expanded_nodes
