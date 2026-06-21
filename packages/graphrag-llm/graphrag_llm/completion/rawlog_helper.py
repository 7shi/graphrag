import os
import re
import threading
from xml.dom.minidom import Document

# Global lock and counter for thread-safe concurrent write control
_log_lock = threading.Lock()
_next_num = 1

def _write_rawlog(messages, response: str):
    """
    Write raw query messages and the assistant response to an XML file.
    """
    global _next_num
    try:
        log_dir = os.environ.get("GRAPHRAG_RAWLOG_DIR", "rawlogs")
        
        # Acquire global lock to prevent race conditions during file name search and write
        with _log_lock:
            os.makedirs(log_dir, exist_ok=True)
            
            # Find the first unused sequential file name
            while True:
                filename = os.path.join(log_dir, f"{_next_num:05d}.xml")
                if not os.path.exists(filename):
                    break
                _next_num += 1
                
            doc = Document()
            messages_el = doc.createElement("messages")
            doc.appendChild(messages_el)

            def escape_cdata_content(s: str) -> str:
                return re.sub(r"\]\](\s*)\>", lambda m: f"]]{m.group(1)} >", s)

            def prepare_text(s: str) -> str:
                if not isinstance(s, str):
                    s = str(s)
                return f"\n{escape_cdata_content(s.rstrip('\n'))}\n"

            # 1. Append query messages
            if isinstance(messages, list):
                for msg in messages:
                    if isinstance(msg, dict):
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        
                        msg_el = doc.createElement("message")
                        msg_el.setAttribute("role", role)
                        cdata = doc.createCDATASection(prepare_text(content))
                        msg_el.appendChild(cdata)
                        messages_el.appendChild(msg_el)
            elif isinstance(messages, str):
                msg_el = doc.createElement("message")
                msg_el.setAttribute("role", "user")
                cdata = doc.createCDATASection(prepare_text(messages))
                msg_el.appendChild(cdata)
                messages_el.appendChild(msg_el)

            # 2. Append assistant response
            if response:
                msg_el = doc.createElement("message")
                msg_el.setAttribute("role", "assistant")
                cdata = doc.createCDATASection(prepare_text(response))
                msg_el.appendChild(cdata)
                messages_el.appendChild(msg_el)

            xml_content = doc.toprettyxml(indent="", encoding="utf-8").decode("utf-8")

            with open(filename, "w", encoding="utf-8") as f:
                f.write(xml_content)
                
            # Increment for the next write operation
            _next_num += 1
    except Exception:
        # Ignore errors to prevent crashing the main GraphRAG execution
        pass

def _wrap_response(response, messages, is_streaming):
    """
    Wrap synchronous response for logging.
    """
    if not is_streaming:
        _write_rawlog(messages, getattr(response, "content", ""))
        return response

    def _stream_wrapper(iterator):
        chunks = []
        for chunk in iterator:
            chunks.append(chunk)
            yield chunk
        full_response = ""
        for chunk in chunks:
            try:
                full_response += chunk.choices[0].delta.content or ""
            except Exception:
                pass
        _write_rawlog(messages, full_response)

    return _stream_wrapper(response)

async def _wrap_response_async(response, messages, is_streaming):
    """
    Wrap asynchronous response for logging.
    """
    if not is_streaming:
        _write_rawlog(messages, getattr(response, "content", ""))
        return response

    async def _stream_wrapper(async_iterator):
        chunks = []
        async for chunk in async_iterator:
            chunks.append(chunk)
            yield chunk
        full_response = ""
        for chunk in chunks:
            try:
                full_response += chunk.choices[0].delta.content or ""
            except Exception:
                pass
        _write_rawlog(messages, full_response)

    return _stream_wrapper(response)
