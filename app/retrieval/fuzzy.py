from __future__ import annotations

import pandas as pd
from rapidfuzz import fuzz


def fuzzy_candidate(df: pd.DataFrame, query_mdc_norm: str) -> pd.DataFrame:
    out = df.copy()
    out["fuzzy_score"] = out["mdc_norm"].map(
        lambda value: fuzz.ratio(query_mdc_norm, value) / 100.0
    )
    return out.sort_values("fuzzy_score", ascending=False)
