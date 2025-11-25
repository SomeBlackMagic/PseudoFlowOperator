def sh_quote(s: str) -> str:
    # Simple POSIX shell escaping
    return "'" + s.replace("'", "'\"'\"'") + "'"
