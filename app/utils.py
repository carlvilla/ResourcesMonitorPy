def _f(val, decimals: int = 1, suffix: str = "") -> str:
    if val is None:
        return "—"
    try:
        return f"{float(val):.{decimals}f}{suffix}"
    except TypeError, ValueError:
        return "—"
