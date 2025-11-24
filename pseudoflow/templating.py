
import re
from typing import Dict

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

def render_str(s: str, vars_map: Dict[str, str]) -> str:
    def repl(m):
        key = m.group(1)
        return str(vars_map.get(key, m.group(0)))
    return _VAR_RE.sub(repl, s)
