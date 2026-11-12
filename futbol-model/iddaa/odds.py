"""Bookmaker margin removal (Shin 1993; Štrumbelj 2014)."""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq


def shin(odds_rows: np.ndarray) -> np.ndarray:
    """Shin implied probabilities for each row of decimal odds (N, k)."""
    out = np.full(odds_rows.shape, np.nan)
    for r, o in enumerate(odds_rows):
        if not np.all(np.isfinite(o)):
            continue
        q = 1.0 / o
        s = q.sum()
        if s <= 1.0:
            out[r] = q / s
            continue

        def f(z):
            p = (np.sqrt(z * z + 4 * (1 - z) * q * q / s) - z) / (2 * (1 - z))
            return p.sum() - 1

        try:
            z = brentq(f, 0.0, 0.4)
        except ValueError:
            out[r] = q / s
            continue
        p = (np.sqrt(z * z + 4 * (1 - z) * q * q / s) - z) / (2 * (1 - z))
        out[r] = p / p.sum()
    return out


def power(odds_rows: np.ndarray) -> np.ndarray:
    """Power method: p_i = q_i^k with k s.t. sum = 1 (good for 2-way markets)."""
    out = np.full(odds_rows.shape, np.nan)
    for r, o in enumerate(odds_rows):
        if not np.all(np.isfinite(o)):
            continue
        q = 1.0 / o
        try:
            k = brentq(lambda k: (q ** k).sum() - 1, 0.5, 2.0)
            out[r] = q ** k
        except ValueError:
            out[r] = q / q.sum()
    return out
