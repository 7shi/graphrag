import sys
import os
import re
import xml.etree.ElementTree as ET

def unescape_cdata_content(s: str) -> str:
    """
    CDATAセクションを回避するために _write_rawlog でエスケープされた "]]>" を元に戻します。
    """
    if not s:
        return ""
    return re.sub(r"\]\]\s*\>", "]]>", s)

def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python rawlog_show.py <path_to_xml_file>")
        sys.exit(1)
        
    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
        
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        
        response_content = ""
        role_info = ""
        
        messages_found = root.findall("message")
        if messages_found:
            # 新構造: 最後の message 要素 (通常は role="assistant") を取得
            last_msg = messages_found[-1]
            response_content = unescape_cdata_content(last_msg.text or "")
            role_info = f" (Role: {last_msg.get('role', 'unknown')})"
        else:
            # 旧構造: <response> 要素を取得
            response_el = root.find("response")
            if response_el is not None:
                response_content = unescape_cdata_content(response_el.text or "")
                role_info = " (Old Format Response)"
                
        if not response_content:
            print("Error: No response content found in the XML file.")
            sys.exit(1)
            
        print(f"=== Response from: {filepath}{role_info} ===")
        print("-" * 60)
        print(response_content.strip())
        print("-" * 60)
        
    except Exception as e:
        print(f"Error parsing XML file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
