"""Small, explainable sampling policy for a minimized InProcess window.

This is a local GUI overhead control, not an OS power-plan optimizer.
No scientific integration step is affected by this monitoring cadence.
"""


def effective_interval_ms(configured_ms: int, *, minimized: bool) -> int:
    """Respect the user setting while limiting hidden monitoring to 3 seconds."""
    if type(configured_ms) is not int or not 250 <= configured_ms <= 10_000:
        raise ValueError("O intervalo de monitorização deve estar entre 250 e 10000 ms.")
    return max(configured_ms, 3_000) if minimized else configured_ms
