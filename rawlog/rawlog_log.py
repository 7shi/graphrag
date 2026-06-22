import sys
import os
import glob
import re
import json
import xml.etree.ElementTree as ET
from llm7shi.compat import generate_with_schema

def unescape_cdata_content(s: str) -> str:
    """
    CDATAセクションを回避するために _write_rawlog でエスケープされた "]]>" を元に戻します。
    例: "]] >" -> "]]>"
    """
    if not s:
        return ""
    # "]]" と ">" の間にあるスペースを削除して元の "]]>" に戻す
    return re.sub(r"\]\]\s*\>", "]]>", s)

def analyze_file(filepath: str) -> str:
    """
    XMLファイルをパースして、messages履歴を復元した上で、要約確認ターンを付け足してローカルLLMに問い合わせます。
    """
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        
        messages_found = root.findall("message")
        if messages_found:
            # 1. 新構造: XML内のメッセージ履歴をそのまま messages リストとして復元
            messages = []
            for msg in messages_found:
                role = msg.get("role", "unknown")
                content = unescape_cdata_content(msg.text or "")
                messages.append({"role": role, "content": content})
            
            # 2. 要約を求める「確認ターン」を付け足し
            messages.append({
                "role": "user",
                "content": "先ほどのやり取りでは何をしているのか、要点を簡潔に日本語で説明してください。"
            })
        else:
            # 旧構造 (<query> と <response>) に対するフォールバック
            query_el = root.find("query")
            response_el = root.find("response")
            if query_el is None or response_el is None:
                return "ERROR: Invalid XML format"
                
            query = unescape_cdata_content(query_el.text or "")
            response_content = unescape_cdata_content(response_el.text or "")
            
            messages = [
                {
                    "role": "system", 
                    "content": "あなたは優秀なAIアシスタントです。提示されたLLMへのクエリと、それに対するレスポンスを分析し、何が行われているのかを分かりやすく解説してください。"
                },
                {"role": "user", "content": f"【クエリ】\n{query.strip()}"},
                {"role": "assistant", "content": f"【レスポンス】\n{response_content.strip()}"},
                {"role": "user", "content": "先ほどのやり取り（クエリとレスポンス）では何をしているのか、要点を簡潔に日本語で説明してください。"}
            ]
            
    except Exception as e:
        return f"ERROR: XML parse failed ({e})"
    
    try:
        # generate_with_schema は実行時にレスポンスストリームを標準出力に流す仕様のため、
        # スクリプト側での復唱（print）は不要です。
        response = generate_with_schema(
            messages,
            model="ollama:gemma4:26b-a4b-it-qat",
            include_thoughts=False,
            show_params=False,
        )
        return response.text
    except Exception as e:
        return f"ERROR: Generation failed ({e})"

def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python rawlog_log.py <directory_path_or_file_path> [output_jsonl_path]")
        sys.exit(1)
        
    target_path = sys.argv[1]
    
    # 1. JSONL出力先の決定 (デフォルトは対象の親ディレクトリ内に配置される同名の .jsonl)
    if len(sys.argv) >= 3:
        jsonl_path = sys.argv[2]
    else:
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
            
        jsonl_path = os.path.join(parent_dir, f"{dir_name}.jsonl")
        
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
    processed_files = set()
    if os.path.exists(jsonl_path):
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        data = json.loads(line_str)
                        if "file" in data:
                            processed_files.add(data["file"])
            print(f"Loaded existing JSONL: Found {len(processed_files)} previously analyzed items.")
        except Exception as e:
            print(f"Warning: Could not read existing JSONL file for resume: {e}")
            
    print(f"Starting analysis for {len(xml_files)} file(s). Output JSONL: {jsonl_path}")
    print("=" * 60)
    
    for filepath in xml_files:
        # スキップ判定
        if filepath in processed_files:
            print(f"[Skipping: {filepath}] (Already analyzed)")
            continue
            
        print(f"\n[Analyzing: {filepath}]")
        print("-" * 50)
        
        # 分析の実行
        result_text = analyze_file(filepath)
        
        # JSONLファイルに随時追記
        try:
            record = {
                "file": filepath,
                "response": result_text
            }
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            processed_files.add(filepath)
        except Exception as e:
            print(f"Error writing to JSONL file: {e}")
            
    print(f"\nAnalysis completed. Results appended to {jsonl_path}")

if __name__ == "__main__":
    main()
