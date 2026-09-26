"""Number formatting used in notes, console output and the PDF."""


def usd(v: float, dp: int = 2) -> str:
    return f"${v:,.{dp}f}" if v is not None else "n/a"


def usd0(v: float) -> str:
    return usd(v, 0)


def sh(v: float, dp: int = 2) -> str:
    """Share counts: whole numbers print without decimals, fractions keep `dp` places."""
    if v is None:
        return "n/a"
    return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.{dp}f}"


def pct(v: float, dp: int = 2) -> str:
    return f"{v * 100:.{dp}f}%" if v is not None else "n/a"


def pp(v: float, dp: int = 2) -> str:
    if v is None:
        return "n/a"
    x = round(v * 100, dp)
    return f"{x:+.{dp}f} pp" if x != 0 else f"{0:.{dp}f} pp"
