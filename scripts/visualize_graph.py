import json
import os

def generate_graph_html(json_path="data/processed/graph/triplets.json", out_path="graph_visualization.html"):
    if not os.path.exists(json_path):
        print(f"Không tìm thấy file {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    triplets = data.get("triplets", [])
    if not triplets:
        print("Không có triplet nào.")
        return

    nodes_set = set()
    edges = []
    
    for idx, t in enumerate(triplets):
        subj = t["subject"]
        obj = t["object"]
        pred = t["predicate"]
        chunk = t.get("chunk_id", "")
        
        nodes_set.add(subj)
        nodes_set.add(obj)
        edges.append({
            "from": subj,
            "to": obj,
            "label": pred,
            "title": f"Chunk ID: {chunk}"
        })

    # Tạo mảng nodes cho Vis.js
    nodes_js = [{"id": n, "label": n} for n in nodes_set]

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Sổ tay Sinh viên - Knowledge Graph Visualization</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style type="text/css">
        body {{
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
            background-color: #f4f7f6;
        }}
        #mynetwork {{
            width: 100vw;
            height: 100vh;
            border: none;
        }}
        #info {{
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(255,255,255,0.9);
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 10;
        }}
    </style>
</head>
<body>
    <div id="info">
        <h3>Knowledge Graph HCMUE</h3>
        <p>Tổng số Đỉnh (Khái niệm): <strong>{len(nodes_set)}</strong></p>
        <p>Tổng số Cạnh (Mối quan hệ): <strong>{len(edges)}</strong></p>
        <p style="font-size: 12px; color: #555;">(Dùng chuột để cuộn phóng to/thu nhỏ. Kéo thả đỉnh để tinh chỉnh)</p>
    </div>
    <div id="mynetwork"></div>

    <script type="text/javascript">
        var nodes = new vis.DataSet({json.dumps(nodes_js, ensure_ascii=False)});
        var edges = new vis.DataSet({json.dumps(edges, ensure_ascii=False)});

        var container = document.getElementById('mynetwork');
        var data = {{
            nodes: nodes,
            edges: edges
        }};
        var options = {{
            nodes: {{
                shape: 'dot',
                size: 15,
                font: {{ size: 14, face: 'Tahoma' }},
                color: {{ background: '#4CAF50', border: '#388E3C' }}
            }},
            edges: {{
                width: 1.5,
                color: {{ color: '#888', highlight: '#2196F3' }},
                arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }},
                font: {{ size: 10, align: 'middle', color: '#d32f2f' }},
                smooth: {{ type: 'continuous' }}
            }},
            physics: {{
                barnesHut: {{
                    gravitationalConstant: -10000,
                    centralGravity: 0.3,
                    springLength: 200,
                    springConstant: 0.04
                }},
                stabilization: {{ iterations: 150 }}
            }}
        }};
        var network = new vis.Network(container, data, options);
    </script>
</body>
</html>
"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"Đã tạo file biểu đồ tại: {os.path.abspath(out_path)}")

if __name__ == "__main__":
    generate_graph_html()
