import json
import pandas as pd
import os
import re
from unidecode import unidecode

def slugify(text):
    if not isinstance(text, str):
        return ""
    text = text.replace('Đ', 'D').replace('đ', 'd')
    text = unidecode(text)
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    words = text.split()
    return "".join(word.capitalize() for word in words)

def process_batch(prefix_excel, prefix_json):
    print(f"\n======================================")
    print(f"Xử lý lô dữ liệu: {prefix_excel}")
    excel_path = f'data/raw/gpt_extracted/{prefix_excel}_extracted.xlsx'
    
    if prefix_json == "K48_49":
        json_path = f'data/processed/chunks/K48-K49_docstore_items.json'
    else:
        json_path = f'data/processed/chunks/{prefix_json}_docstore_items.json'
        
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        print(f"Lỗi đọc file Excel {excel_path}: {e}")
        return []

    excel_map = {}
    for idx, row in df.iterrows():
        ten_dieu = str(row.get('Ten_dieu', '')) if pd.notna(row.get('Ten_dieu', '')) else ""
        dieu_raw = row.get('Dieu', '')
        dieu = str(dieu_raw).replace(".", "").strip() if pd.notna(dieu_raw) else ""
        
        # Bắt khóa kép: Điều + Trang (Giúp chống ghi đè chéo văn bản)
        trang_raw = row.get('Trang')
        trang_str = ""
        if pd.notna(trang_raw):
            try:
                trang_str = str(int(float(trang_raw)))
            except:
                trang_str = str(trang_raw).strip()

        comp_key = f"{dieu}_{trang_str}"
        
        excel_map[comp_key] = {
            'khoa': str(row.get('Khoa', '')).strip() if pd.notna(row.get('Khoa', '')) else "",
            'ten_van_ban': str(row.get('Ten_van_ban', '')).strip() if pd.notna(row.get('Ten_van_ban', '')) else "",
            'chuong': str(row.get('Chuong', '')).strip() if pd.notna(row.get('Chuong', '')) else "",
            'ten_dieu': ten_dieu
        }
        
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
    except Exception as e:
        print(f"Lỗi đọc file JSON {json_path}: {e}")
        return []

    matched_count = 0
    updated_chunks = []
    
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        article_str = metadata.get("article", "")
        if not article_str:
            continue
            
        clean_article = article_str.replace(".", "").strip()
        
        # Lấy trang từ chunk
        source_pages = metadata.get("source_pages", [])
        trang_str = ""
        if source_pages and len(source_pages) > 0:
            trang_str = str(int(source_pages[0]))
            
        comp_key = f"{clean_article}_{trang_str}"
        
        if comp_key in excel_map:
            matched_count += 1
            info = excel_map[comp_key]
            
            khoa_slug = info['khoa'].replace("_", "-") 
            van_ban_slug = slugify(info['ten_van_ban'])
            chuong_slug = slugify(info['chuong'])
            dieu_slug = slugify(clean_article)
            
            uniform_id = f"{khoa_slug}_{van_ban_slug}"
            if chuong_slug:
                uniform_id += f"_{chuong_slug}"
            uniform_id += f"_{dieu_slug}"
            
            chunk["_id"] = uniform_id
            chunk["metadata"]["document_title"] = info['ten_van_ban']
            chunk["metadata"]["chapter"] = info['chuong']
            chunk["metadata"]["parent_section_id"] = uniform_id 
            
            header_tag = f"[ID CHUẨN: {uniform_id} | {khoa_slug} | {info['ten_van_ban']} | {info['chuong']}]\n"
            
            if header_tag not in chunk["content"]:
                chunk["content"] = header_tag + chunk["content"]
            if header_tag not in chunk["normalized_content"]:
                chunk["normalized_content"] = header_tag + chunk["normalized_content"]
                
            for table in chunk.get("tables", []):
                table_kind = table.get("table_kind", "table")
                table["table_id"] = f"{uniform_id}_{table_kind}"
                
            updated_chunks.append(chunk)

    print(f"Matched {matched_count}/{len(chunks)} chunks using Composite Key (Dieu + Trang).")
    return updated_chunks

def main():
    batches = [
        ("K48_49", "K48_49"),
        ("K50", "K50"),
        ("K51", "K51")
    ]
    
    all_chunks = []
    for excel, json_file in batches:
        result = process_batch(excel, json_file)
        all_chunks.extend(result)
        
    print(f"\n======================================")
    print(f"Tổng cộng {len(all_chunks)} khối văn bản Vàng đã được ép ID thành công!")
    
    output_file = 'data/processed/chunks/all_docstore_items.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
    print(f"Đã lưu toàn bộ dữ liệu Vàng vào {output_file}")

if __name__ == "__main__":
    main()
