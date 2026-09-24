def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average of a series."""
    y = 0.0
    for v in x:
        y = alpha * v + (1 - alpha) * y
    return y
