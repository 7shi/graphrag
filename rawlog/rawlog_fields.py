import sys
import argparse
import os
import glob
import re
import json
import xml.etree.ElementTree as ET
from collections import defaultdict

def unescape_cdata_content(s: str) -> str:
    """
    CDATAセクションを回避するために _write_rawlog でエスケープされた "]]>" を元に戻します。
    """
    if not s:
        return ""
    return re.sub(r"\]\]\s*\>", "]]>", s)

def extract_json_and_keys(text: str) -> tuple[str, list[str]]:
    """
    レスポンス文字列からJSONを検出し、パース可能ならそのトップレベルのキー（フィールド）を抽出します。
    """
    text = text.strip()
    if not text:
        return "text", []

    # 1. ```json ... ``` の Markdown 記述からの抽出を試みる
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        try:
            obj = json.loads(json_match.group(1))
            if isinstance(obj, dict):
                return "json", list(obj.keys())
        except Exception:
            pass

    # 2. ``` ... ``` (言語指定なし) の Markdown 記述からの抽出を試みる
    json_match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        try:
            obj = json.loads(json_match.group(1))
            if isinstance(obj, dict):
                return "json", list(obj.keys())
        except Exception:
            pass

    # 3. 最も外側にある中括弧 { } を探して抽出・パースを試みる
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        potential_json = text[start_idx:end_idx+1]
        try:
            obj = json.loads(potential_json)
            if isinstance(obj, dict):
                return "json", list(obj.keys())
        except Exception:
            pass

    # 4. 全体の直接パースを試みる
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return "json", list(obj.keys())
    except Exception:
        pass

    return "text", []

def analyze_file_fields(filepath: str) -> tuple[str, list[str]]:
    """
    XMLログの 最後のmessage要素 を解析し、JSONかどうかとフィールド名の一覧を返します。
    """
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        
        # 新しい <messages> XML構造のパース (最後のmessageを response と見なす)
        response_content = ""
        messages_found = root.findall("message")
        if messages_found:
            last_msg = messages_found[-1]
            response_content = unescape_cdata_content(last_msg.text or "")
        else:
            # 旧構造 (<response>) に対するフォールバック
            response_el = root.find("response")
            if response_el is not None:
                response_content = unescape_cdata_content(response_el.text or "")
                
        if not response_content:
            return "error_invalid_xml", []
            
        return extract_json_and_keys(response_content)
    except Exception:
        return "error_parse_failed", []

def main():
    parser = argparse.ArgumentParser(description="XMLログのレスポンスJSONをフィールド別にグループ化します。")
    parser.add_argument("target", help="ディレクトリまたはXMLファイルのパス")
    parser.add_argument("output_jsonl", nargs="?", help="出力JSOLパス（省略時は自動生成）")
    parser.add_argument("output_groups", nargs="?", help="グループ化結果テキストのパス（省略時は自動生成）")
    args = parser.parse_args()

    target_path = args.target

    # 1. 出力先の決定 (デフォルトは対象親ディレクトリ内の <名前>-fields.jsonl と <名前>-groups.txt)
    norm_path = target_path.rstrip(os.sep)
    if os.path.isdir(target_path):
        dir_name = os.path.basename(norm_path)
        parent_dir = os.path.dirname(norm_path)
    else:
        dir_name = os.path.basename(os.path.dirname(norm_path))
        parent_dir = os.path.dirname(os.path.dirname(norm_path))

    if not dir_name:
        dir_name = "analysis_results"
        parent_dir = "."

    jsonl_path = args.output_jsonl or os.path.join(parent_dir, f"{dir_name}-fields.jsonl")
    groups_txt_path = args.output_groups or os.path.join(parent_dir, f"{dir_name}-groups.txt")
        
    # 2. 対象ファイルのリスト化
    if os.path.isdir(target_path):
        xml_files = sorted(glob.glob(os.path.join(target_path, "*.xml")))
        if not xml_files:
            print(f"No XML files found in directory: {target_path}")
            sys.exit(1)
    elif os.path.isfile(target_path):
        xml_files = [target_path]
    else:
        print(f"Error: Target path not found: {target_path}")
        sys.exit(1)
        
    # 3. 既存のJSONLがある場合は読み込んで、すでに処理済みのファイルを特定
    all_records = []
    processed_files = set()
    if os.path.exists(jsonl_path):
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        data = json.loads(line_str)
                        all_records.append(data)
                        if "file" in data:
                            processed_files.add(data["file"])
            print(f"Loaded existing JSONL: Found {len(processed_files)} previously analyzed items.")
        except Exception as e:
            print(f"Warning: Could not read existing JSONL file for resume: {e}")
            
    print(f"Starting field extraction for {len(xml_files)} file(s). Output: {jsonl_path}")
    print("=" * 60)
    
    # 4. 未処理のファイルを解析して追記
    for filepath in xml_files:
        if filepath in processed_files:
            # 既にロード済みのためスキップ
            continue
            
        file_type, fields = analyze_file_fields(filepath)
        
        record = {
            "file": filepath,
            "type": file_type,
            "fields": fields
        }
        
        try:
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            all_records.append(record)
            processed_files.add(filepath)
            print(f"Extracted: {filepath} -> type: {file_type}, fields: {fields}")
        except Exception as e:
            print(f"Error writing to JSONL file: {e}")
            
    def compress_filenames(filenames: list[str]) -> list[str]:
        def get_num_and_ext(filename):
            match = re.match(r"(\d+)(\.xml)", filename)
            if match:
                return int(match.group(1)), len(match.group(1)), match.group(2)
            return None

        parsed = []
        unparsed = []
        for f in filenames:
            info = get_num_and_ext(f)
            if info:
                parsed.append((info[0], info[1], info[2], f))
            else:
                unparsed.append(f)
                
        if not parsed:
            return sorted(unparsed)
            
        parsed.sort(key=lambda x: x[0])
        
        ranges = []
        start_num, width, ext, start_orig = parsed[0]
        prev_num = start_num
        
        for i in range(1, len(parsed)):
            num, w, e, orig = parsed[i]
            if num == prev_num + 1 and w == width and e == ext:
                prev_num = num
            else:
                ranges.append((start_num, prev_num, width, ext, start_orig))
                start_num = num
                width = w
                ext = e
                start_orig = orig
                prev_num = num
                
        ranges.append((start_num, prev_num, width, ext, start_orig))
        
        compressed = []
        for start, end, w, e, start_orig in ranges:
            if start == end:
                compressed.append(start_orig)
            else:
                compressed.append(f"{{{start:0{w}d}..{end:0{w}d}}}{e}")
                
        return compressed + sorted(unparsed)

    # 5. 同じフィールドでグループ化して標準出力に表示＆テキストファイルに保存
    output_lines = []
    output_lines.append("=== フィールドグループ化結果 ===")
    output_lines.append(f"\n対象ディレクトリ: {target_path}")
    
    groups = defaultdict(list)
    text_files = []
    
    for rec in all_records:
        if rec.get("type") == "json":
            key = tuple(rec.get("fields", []))
            groups[key].append(rec.get("file"))
        else:
            text_files.append(rec.get("file"))
            
    sorted_groups = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)
    group_idx = 1
    
    for fields_tuple, files in sorted_groups:
        fields_str = ", ".join(f'"{f}"' for f in fields_tuple)
        output_lines.append(f"\nGroup {group_idx}: [ {fields_str} ] ({len(files)} files)")
        basenames = [os.path.basename(f) for f in files]
        for f in compress_filenames(basenames):
            output_lines.append(f"  - {f}")
        group_idx += 1
        
    if text_files:
        output_lines.append(f"\nGroup {group_idx} (Non-JSON / Text / Errors): ({len(text_files)} files)")
        basenames = [os.path.basename(f) for f in text_files]
        for f in compress_filenames(basenames):
            output_lines.append(f"  - {f}")
            
    output_content = "\n".join(output_lines) + "\n"
    
    # 標準出力に表示
    print(output_content)
    
    # テキストファイルに保存
    try:
        with open(groups_txt_path, "w", encoding="utf-8") as f:
            f.write(output_content)
        print(f"Grouped results saved to {groups_txt_path}")
    except Exception as e:
        print(f"Error writing to groups file: {e}")
            
    print(f"\nField analysis completed. Records saved to {jsonl_path}")

if __name__ == "__main__":
    main()
