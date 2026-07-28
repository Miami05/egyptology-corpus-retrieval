from __future__ import annotations

import pandas as pd


def exact_match_candidates(df: pd.DataFrame, query_mdc_norm: str) -> pd.DataFrame:
    mask = df["mdc_norm"] == query_mdc_norm
    return df.loc[mask].copy()
