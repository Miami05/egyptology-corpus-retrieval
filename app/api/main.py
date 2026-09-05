from __future__ import annotations

import functools

from typing import Annotated, cast

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

from app.core.config import settings
from app.data.loader import load_examples_csv
from app.services.retrieval import SearchIndex, build_search_index, retrieve_top_k

app = FastAPI(title=settings.app_name)

DATA_PATH = "data/processed/examples.csv"


@functools.lru_cache(maxsize=1)
def load_corpus() -> tuple[pd.DataFrame, SearchIndex]:
    """The corpus frame and its `SearchIndex`, built once and reused.

    The endpoint used to call `load_examples_csv` and then `retrieve_top_k` with no
    index on every request — so every request paid the ~9 s CSV load and, worse, took
    retrieval's scalar path (~3 s) instead of the batched one the UI gets from a
    `SearchIndex`. Building both once here (lazily, so importing this module for a test
    costs nothing) hands `retrieve_top_k` the same index the Streamlit path uses.
    """
    df = load_examples_csv(DATA_PATH)
    return df, build_search_index(df)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


@app.get("/examples/search")
def search_examples(
    query_mdc: Annotated[
        str,
        Query(
            min_length=1,
            description="MdC, transliteration, or sign sequence to search for.",
        ),
    ],
    k: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of ranked corpus matches to return.",
        ),
    ] = 3,
) -> dict:
    df, index = load_corpus()
    results = retrieve_top_k(df, query_mdc, k=k, index=index)
    if results.empty:
        raise HTTPException(status_code=404, detail="No results found")
    columns = [
        "source",
        "source_text_id",
        "source_sentence_id",
        "mdc",
        "sign_sequence",
        "transliteration_gold",
        "translation",
        "final_score",
        "evidence",
    ]
    result_df = cast(pd.DataFrame, results.loc[:, columns])
    return {
        "query": query_mdc,
        "results": result_df.to_dict(orient="records"),
    }
