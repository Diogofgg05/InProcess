def temperatures() -> float | None:
    """psutil does not expose Windows CPU temperature. No invented fallback."""
    return None
