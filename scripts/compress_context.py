"""
Lightweight context compressor (Headroom fallback since headroom-ai not on PyPI 3.9).
Deduplicates and truncates large API responses before feeding to prompts.
"""
import json, re

def compress_json(data: dict | list, max_keys: int = 20) -> str:
    """Strip nulls, truncate arrays, pretty print."""
    def _trim(obj, depth=0):
        if depth > 4:
            return "..."
        if isinstance(obj, list):
            trimmed = [_trim(x, depth+1) for x in obj[:max_keys]]
            if len(obj) > max_keys:
                trimmed.append(f"... +{len(obj)-max_keys} more")
            return trimmed
        if isinstance(obj, dict):
            return {k: _trim(v, depth+1) for k, v in obj.items() if v is not None}
        return obj
    return json.dumps(_trim(data), indent=2)

def deduplicate_lines(text: str) -> str:
    """Remove consecutive duplicate log lines."""
    lines = text.splitlines()
    seen, out = set(), []
    for line in lines:
        key = re.sub(r'\d+', 'N', line.strip())
        if key not in seen:
            seen.add(key)
            out.append(line)
    return "\n".join(out)

if __name__ == "__main__":
    import sys
    text = sys.stdin.read()
    try:
        data = json.loads(text)
        print(compress_json(data))
    except json.JSONDecodeError:
        print(deduplicate_lines(text))
