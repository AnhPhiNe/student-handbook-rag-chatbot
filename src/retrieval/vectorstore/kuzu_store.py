import json
import logging
import os
import shutil
from typing import List, Dict, Any

import kuzu

# Khởi tạo logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("kuzu_store")

class KuzuGraphStore:
    def __init__(self, db_path: str = "data/processed/kuzu_db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        logger.info(f"Khởi tạo KuzuDB tại {self.db_path}")
        self.db = kuzu.Database(self.db_path)
        self.conn = kuzu.Connection(self.db)
        
        self._init_schema()

    def _init_schema(self):
        """Khởi tạo cấu trúc bảng cho Đồ thị (Nodes và Edges)"""
        try:
            # Bảng Node: Concept (Khái niệm)
            self.conn.execute("CREATE NODE TABLE IF NOT EXISTS Concept (name STRING, PRIMARY KEY (name))")
            
            # Bảng Edge: RelatedTo (Mối quan hệ)
            self.conn.execute("CREATE REL TABLE IF NOT EXISTS RelatedTo (FROM Concept TO Concept, predicate STRING, chunk_id STRING)")
            
            logger.info("Schema KuzuDB đã sẵn sàng.")
        except RuntimeError as e:
            # Kuzu có thể văng lỗi nếu table đã tồn tại, ta bỏ qua
            logger.debug(f"Schema có thể đã tồn tại: {e}")

    def import_triplets(self, json_path: str):
        """Nhập hàng loạt Triplets từ file JSON vào KuzuDB"""
        if not os.path.exists(json_path):
            logger.error(f"Không tìm thấy file {json_path}")
            return
            
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        triplets = data.get("triplets", [])
        if not triplets:
            logger.warning("File JSON không chứa triplet nào.")
            return

        logger.info(f"Bắt đầu nạp {len(triplets)} bộ ba vào Đồ thị...")
        
        # 1. Thu thập tất cả các Node duy nhất (Tránh lỗi trùng lặp khi Insert)
        nodes = set()
        for t in triplets:
            nodes.add(t["subject"])
            nodes.add(t["object"])
            
        # 2. Insert Nodes (Dùng câu lệnh Cypher MERGE)
        logger.info(f"Đang tạo {len(nodes)} đỉnh (Nodes)...")
        for node in nodes:
            # Escape single quotes in node names
            safe_node = node.replace("'", "\\'")
            self.conn.execute(f"MERGE (c:Concept {{name: '{safe_node}'}})")
            
        # 3. Insert Edges (Tạo quan hệ)
        logger.info(f"Đang tạo {len(triplets)} cạnh (Edges)...")
        for t in triplets:
            safe_sub = t["subject"].replace("'", "\\'")
            safe_obj = t["object"].replace("'", "\\'")
            safe_pred = t["predicate"].replace("'", "\\'")
            safe_chunk = t["chunk_id"].replace("'", "\\'")
            
            query = f"""
            MATCH (a:Concept {{name: '{safe_sub}'}}), (b:Concept {{name: '{safe_obj}'}})
            CREATE (a)-[:RelatedTo {{predicate: '{safe_pred}', chunk_id: '{safe_chunk}'}}]->(b)
            """
            self.conn.execute(query)
            
        logger.info("Nạp Đồ thị hoàn tất!")

    def clear_database(self):
        """Xóa toàn bộ CSDL để làm lại từ đầu"""
        logger.warning(f"Đang xóa CSDL tại {self.db_path}...")
        del self.conn
        del self.db
        import shutil
        import os
        import time
        if os.path.exists(self.db_path):
            if os.path.isfile(self.db_path):
                os.remove(self.db_path)
            else:
                shutil.rmtree(self.db_path)
            time.sleep(1)
        # Re-init
        self.db = kuzu.Database(self.db_path)
        self.conn = kuzu.Connection(self.db)
        self._init_schema()

    def get_subgraph(self, entities: List[str], depth: int = 2, cohort: str = None) -> List[Dict[str, Any]]:
        """Truy xuất mạng lưới đồ thị lân cận bằng duyệt đồ thị thủ công để an toàn struct"""
        if not entities:
            return []
            
        results = []
        visited_nodes = set()
        queue = [(e, 0) for e in entities]
        
        while queue:
            current_node, current_depth = queue.pop(0)
            if current_depth >= depth or current_node in visited_nodes:
                continue
                
            visited_nodes.add(current_node)
            safe_node = current_node.replace("'", "\\'")
            
            # Quét các cạnh lân cận trực tiếp (Depth=1)
            where_clause = ""
            if cohort:
                safe_cohort = cohort.replace("'", "\\'")
                where_clause = f"WHERE r.chunk_id CONTAINS '{safe_cohort}'"
                
            query = f"""
            MATCH (a:Concept {{name: '{safe_node}'}})-[r:RelatedTo]-(b:Concept)
            {where_clause}
            RETURN a.name, r.predicate, b.name, r.chunk_id
            LIMIT 50
            """
            try:
                res = self.conn.execute(query)
                while res.has_next():
                    row = res.get_next()
                    source_name = row[0]
                    predicate = row[1]
                    target_name = row[2]
                    chunk_id = row[3]
                    
                    results.append({
                        "source": source_name,
                        "predicate": predicate,
                        "target": target_name,
                        "chunk_id": chunk_id
                    })
                    
                    # Thêm node đích vào queue để quét tiếp nếu cần
                    if target_name not in visited_nodes:
                        queue.append((target_name, current_depth + 1))
                        
            except Exception as e:
                logger.error(f"Lỗi khi truy vấn đồ thị: {e}")
                
        # Lọc trùng lặp
        unique_results = []
        seen = set()
        for r in results:
            key = f"{r['source']}-{r['predicate']}-{r['target']}"
            if key not in seen:
                seen.add(key)
                unique_results.append(r)
                
        return unique_results
