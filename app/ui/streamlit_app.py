from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.data.loader import load_examples_csv
from app.services.annotations import save_annotation
from app.services.evaluation import evaluate_benchmark, load_benchmark_csv
from app.services.retrieval import retrieve_top_k
from app.services.suggestions import suggest_top_readings
from app.storage.bootstrap import ensure_corpus_ready
from app.storage.db import SessionLocal
from app.storage.repo import AnnotationRepo
from app.ui.review_common import (
    annotation_history_to_df,
    attach_db_ids,
    build_reviewed_export_csv,
    build_row_key,
    coerce_bool,
    safe_str,
    score_breakdown_lines,
)

DATA_PATH = "data/processed/examples.csv"
BENCHMARK_PATH = "data/benchmarks/phase3_eval_queries.csv"


# These helpers are shared with the Whyptology workspace so the two front ends
# cannot drift apart. _safe_str/_coerce_bool keep their original local names.
_safe_str = safe_str
_coerce_bool = coerce_bool


st.set_page_config(page_title=settings.app_name, layout="wide")
st.title(settings.app_name)
st.caption("Middle Egyptian contextual transliteration + annotation MVP — Phase 4 readiness")

df = load_examples_csv(DATA_PATH)
# The database file is gitignored, so a fresh deployment has to build and seed it
# before attach_db_ids can look up per-row ids.
ensure_corpus_ready(df)
df = attach_db_ids(df)

# Clean display-only boolean column for Streamlit tables
if "aesthetic_arrangement_flag_bool" in df.columns:
    df["aesthetic_arrangement_flag_display"] = (
        df["aesthetic_arrangement_flag_bool"].fillna(False).astype(bool)
    )
else:
    df["aesthetic_arrangement_flag_display"] = False

with st.sidebar:
    st.header("Project actions")

    export_csv = build_reviewed_export_csv()
    st.download_button(
        label="Download reviewed annotations CSV",
        data=export_csv,
        file_name="reviewed_annotations_export.csv",
        mime="text/csv",
    )

    st.markdown("---")
    st.markdown(f"**Loaded rows:** {len(df)}")
    st.markdown(f"**Top K:** {settings.top_k}")

search_tab, eval_tab = st.tabs(["Search & annotate", "Benchmark evaluation"])

with search_tab:
    left, right = st.columns([1, 1])

    with left:
        st.subheader("Query")
        query_mdc = st.text_area("Paste MdC / sign sequence", height=120)
        query_reading_order = st.text_area(
            "Optional normalized reading order",
            height=100,
            help="Use this when visual arrangement differs from the intended reading order.",
        )

        if st.button(f"Get top {settings.top_k} suggestions"):
            if query_mdc.strip():
                retrieval_pool = retrieve_top_k(
                    df,
                    query_mdc=query_mdc,
                    query_reading_order=query_reading_order,
                    k=max(settings.top_k, 25),
                )
                results = retrieval_pool.head(settings.top_k).copy()
                suggestions = suggest_top_readings(
                    retrieval_pool,
                    query_mdc=query_mdc,
                    query_reading_order=query_reading_order,
                    top_n=3,
                )
                st.session_state["results"] = results
                st.session_state["reading_suggestions"] = suggestions
            else:
                st.warning("Please enter MdC or sign sequence.")

        st.subheader("Examples preview")
        preview_cols = [
            "id",
            "source",
            "source_text_id",
            "source_sentence_id",
            "mdc",
            "transliteration_gold",
            "language_stage",
            "script_type",
            "formula_type",
            "deity",
            "offering_items",
            "normalized_reading_order",
            "aesthetic_arrangement_flag_display",
        ]
        existing_cols = [col for col in preview_cols if col in df.columns]
        st.dataframe(df.loc[:, existing_cols].head(30), width="stretch")

    with right:
        st.subheader("Top 3 suggested readings")

        results = st.session_state.get("results")
        reading_suggestions = st.session_state.get("reading_suggestions", [])

        if reading_suggestions:
            for rank, suggestion in enumerate(reading_suggestions, start=1):
                with st.container(border=True):
                    st.markdown(
                        f"**{rank}. {suggestion.candidate_transliteration}**"
                    )
                    st.metric(
                        "Confidence score",
                        f"{suggestion.confidence_score:.3f}",
                    )
                    st.markdown(
                        f"**Evidence summary:** {suggestion.evidence_summary}"
                    )
                    st.markdown(
                        f"**Supporting examples:** {suggestion.supporting_example_count}"
                    )
                    if suggestion.supporting_sources:
                        st.markdown("**Supporting corpus examples:**")
                        for source_label in suggestion.supporting_sources:
                            st.write(f"- {source_label}")
        elif results is not None:
            st.info("No reading suggestions could be grouped from the current corpus.")
        else:
            st.info("Run a query to see suggested readings.")

        st.subheader("Detailed corpus parallels")

        if results is not None and not results.empty:
            results = results.reset_index(drop=True)

            for i, (_, row) in enumerate(results.iterrows()):
                row_id = row.get("id")
                example_id_value = int(row_id) if pd.notna(row_id) else None
                display_id = example_id_value if example_id_value is not None else "N/A"
                row_key = build_row_key(row, i)

                latest_annotation = None
                history_df = pd.DataFrame()

                if example_id_value is not None:
                    session = SessionLocal()
                    try:
                        annotation_repo = AnnotationRepo(session)
                        latest_annotation = annotation_repo.get_latest_for_example(
                            example_id_value
                        )
                        history_rows = annotation_repo.list_for_example(
                            example_id_value
                        )
                        history_df = annotation_history_to_df(history_rows)
                    finally:
                        session.close()

                with st.container(border=True):
                    st.markdown(f"**Example ID:** {display_id}")
                    st.markdown(f"**Source:** {_safe_str(row.get('source'))}")
                    st.markdown(
                        f"**Source text ID:** {_safe_str(row.get('source_text_id'))}"
                    )
                    st.markdown(
                        f"**Source sentence ID:** {_safe_str(row.get('source_sentence_id'))}"
                    )
                    st.markdown(
                        f"**Language stage:** {_safe_str(row.get('language_stage'))}"
                    )
                    st.markdown(f"**Script type:** {_safe_str(row.get('script_type'))}")
                    st.markdown(f"**MdC:** `{_safe_str(row.get('mdc'))}`")
                    st.markdown(f"**Hieroglyphs:** {_safe_str(row.get('hieroglyphs'))}")
                    st.markdown(
                        f"**Sign sequence:** {_safe_str(row.get('sign_sequence'))}"
                    )
                    st.markdown(
                        f"**Transliteration:** {_safe_str(row.get('transliteration_gold'))}"
                    )
                    st.markdown(f"**Translation:** {_safe_str(row.get('translation'))}")
                    st.markdown(f"**Evidence:** {_safe_str(row.get('evidence'))}")

                    st.markdown("### Base research fields")
                    st.markdown(
                        f"**Display sequence:** {_safe_str(row.get('display_sequence'))}"
                    )
                    st.markdown(
                        f"**Normalized reading order:** {_safe_str(row.get('normalized_reading_order'))}"
                    )
                    st.markdown(
                        f"**Alternate transliterations:** {_safe_str(row.get('alt_transliterations'))}"
                    )
                    st.markdown(
                        f"**Lemma sequence:** {_safe_str(row.get('lemma_sequence'))}"
                    )
                    st.markdown(f"**UPOS:** {_safe_str(row.get('upos'))}")
                    st.markdown(f"**Glossing:** {_safe_str(row.get('glossing'))}")
                    st.markdown(
                        f"**Variant writing note:** {_safe_str(row.get('variant_writing_note'))}"
                    )
                    st.markdown(
                        f"**Morphology note:** {_safe_str(row.get('morphology_note'))}"
                    )
                    st.markdown(f"**Syntax note:** {_safe_str(row.get('syntax_note'))}")
                    st.markdown(
                        f"**Aesthetic arrangement flag:** {bool(row.get('aesthetic_arrangement_flag_bool', False))}"
                    )

                    with st.expander("Scoring breakdown"):
                        for line in score_breakdown_lines(row):
                            st.write(line)

                    st.markdown("---")
                    st.markdown("### Latest annotation")

                    if latest_annotation is None:
                        st.info("No annotation saved yet for this example.")
                    else:
                        st.markdown(f"**Status:** {latest_annotation.status}")
                        st.markdown(
                            f"**Transliteration:** {latest_annotation.transliteration}"
                        )
                        st.markdown(
                            f"**Display sequence:** {_safe_str(latest_annotation.display_sequence)}"
                        )
                        st.markdown(
                            f"**Normalized reading order:** {_safe_str(latest_annotation.normalized_reading_order)}"
                        )
                        st.markdown(
                            f"**Alternate transliterations:** {_safe_str(latest_annotation.alt_transliterations)}"
                        )
                        st.markdown(
                            f"**Variant writing note:** {_safe_str(latest_annotation.variant_writing_note)}"
                        )
                        st.markdown(
                            f"**Morphology note:** {_safe_str(latest_annotation.morphology_note)}"
                        )
                        st.markdown(
                            f"**Syntax note:** {_safe_str(latest_annotation.syntax_note)}"
                        )
                        st.markdown(
                            f"**Aesthetic arrangement flag:** {bool(latest_annotation.aesthetic_arrangement_flag)}"
                        )
                        st.markdown(
                            f"**Uncertainty note:** {_safe_str(latest_annotation.uncertainty_note)}"
                        )
                        st.markdown(
                            f"**Grammar note:** {_safe_str(latest_annotation.grammar_note)}"
                        )
                        st.markdown(f"**Saved at:** {latest_annotation.created_at}")

                    st.markdown("---")
                    st.markdown("### Save expert annotation")

                    default_translit = (
                        latest_annotation.transliteration
                        if latest_annotation is not None
                        else _safe_str(row.get("transliteration_gold"))
                    )
                    default_uncertainty = (
                        latest_annotation.uncertainty_note
                        if latest_annotation is not None
                        else ""
                    )
                    default_grammar = (
                        latest_annotation.grammar_note
                        if latest_annotation is not None
                        else ""
                    )
                    default_status = (
                        latest_annotation.status
                        if latest_annotation is not None
                        else "accepted"
                    )
                    default_display_sequence = (
                        latest_annotation.display_sequence
                        if latest_annotation is not None
                        else _safe_str(row.get("display_sequence"))
                    )
                    default_normalized_reading_order = (
                        latest_annotation.normalized_reading_order
                        if latest_annotation is not None
                        else _safe_str(row.get("normalized_reading_order"))
                    )
                    default_alt_transliterations = (
                        latest_annotation.alt_transliterations
                        if latest_annotation is not None
                        else _safe_str(row.get("alt_transliterations"))
                    )
                    default_variant_writing_note = (
                        latest_annotation.variant_writing_note
                        if latest_annotation is not None
                        else _safe_str(row.get("variant_writing_note"))
                    )
                    default_morphology_note = (
                        latest_annotation.morphology_note
                        if latest_annotation is not None
                        else _safe_str(row.get("morphology_note"))
                    )
                    default_syntax_note = (
                        latest_annotation.syntax_note
                        if latest_annotation is not None
                        else _safe_str(row.get("syntax_note"))
                    )
                    default_aesthetic_flag = (
                        bool(latest_annotation.aesthetic_arrangement_flag)
                        if latest_annotation is not None
                        else bool(row.get("aesthetic_arrangement_flag_bool", False))
                    )

                    status_options = ["accepted", "edited", "rejected", "uncertain"]
                    default_status_index = (
                        status_options.index(default_status)
                        if default_status in status_options
                        else 0
                    )

                    translit = st.text_input(
                        "Edited transliteration",
                        value=default_translit,
                        key=f"translit_{row_key}",
                    )
                    display_sequence = st.text_input(
                        "Display / visual sequence",
                        value=default_display_sequence,
                        key=f"display_sequence_{row_key}",
                    )
                    normalized_reading_order = st.text_input(
                        "Normalized reading order",
                        value=default_normalized_reading_order,
                        key=f"normalized_reading_order_{row_key}",
                    )
                    alt_transliterations = st.text_input(
                        "Alternate transliterations (pipe-separated)",
                        value=default_alt_transliterations,
                        key=f"alt_transliterations_{row_key}",
                    )
                    variant_writing_note = st.text_input(
                        "Variant writing note",
                        value=default_variant_writing_note,
                        key=f"variant_writing_note_{row_key}",
                    )
                    morphology_note = st.text_input(
                        "Morphology note",
                        value=default_morphology_note,
                        key=f"morphology_note_{row_key}",
                    )
                    syntax_note = st.text_input(
                        "Syntax note",
                        value=default_syntax_note,
                        key=f"syntax_note_{row_key}",
                    )
                    aesthetic_arrangement_flag_key = (
                        f"aesthetic_arrangement_flag_{row_key}"
                    )
                    aesthetic_arrangement_flag = st.checkbox(
                        "Aesthetic arrangement affects order",
                        value=default_aesthetic_flag,
                        key=aesthetic_arrangement_flag_key,
                    )
                    uncertainty = st.text_input(
                        "Uncertainty note",
                        value=default_uncertainty,
                        key=f"uncertainty_{row_key}",
                    )
                    grammar = st.text_input(
                        "Grammar note",
                        value=default_grammar,
                        key=f"grammar_{row_key}",
                    )
                    status = st.selectbox(
                        "Status",
                        status_options,
                        index=default_status_index,
                        key=f"status_{row_key}",
                    )

                    if st.button(
                        f"Save annotation {display_id}", key=f"save_{row_key}"
                    ):
                        if example_id_value is None:
                            st.error(
                                "This row still has no SQLite ID. Rebuild and reimport the database first."
                            )
                        else:
                            session = SessionLocal()
                            try:
                                repo = AnnotationRepo(session)
                                aesthetic_arrangement_flag_to_save = _coerce_bool(
                                    st.session_state.get(
                                        aesthetic_arrangement_flag_key,
                                        aesthetic_arrangement_flag,
                                    )
                                )
                                save_annotation(
                                    repo=repo,
                                    example_id=example_id_value,
                                    transliteration=translit,
                                    uncertainty_note=uncertainty or "",
                                    grammar_note=grammar or "",
                                    status=status,
                                    display_sequence=display_sequence or "",
                                    normalized_reading_order=normalized_reading_order
                                    or "",
                                    alt_transliterations=alt_transliterations or "",
                                    variant_writing_note=variant_writing_note or "",
                                    morphology_note=morphology_note or "",
                                    syntax_note=syntax_note or "",
                                    aesthetic_arrangement_flag=(
                                        aesthetic_arrangement_flag_to_save
                                    ),
                                )
                                st.success(
                                    f"Annotation saved for example ID {example_id_value}."
                                )
                                st.rerun()
                            finally:
                                session.close()

                    st.markdown("---")
                    st.markdown("### Annotation history")

                    if history_df.empty:
                        st.info("No history yet.")
                    else:
                        st.dataframe(history_df, width="stretch")
        else:
            st.info("Run a query to see detailed corpus parallels.")

with eval_tab:
    st.subheader("Benchmark evaluation")

    benchmark_path = Path(BENCHMARK_PATH)
    if not benchmark_path.exists():
        st.warning(
            "No benchmark file found yet. Create data/benchmarks/phase3_eval_queries.csv first."
        )
    else:
        benchmark_df = load_benchmark_csv(BENCHMARK_PATH)
        st.markdown(f"**Benchmark rows:** {len(benchmark_df)}")

        if st.button("Run benchmark evaluation"):
            summary, details_df = evaluate_benchmark(
                examples_df=df,
                benchmark_df=benchmark_df,
                k=settings.top_k,
            )
            st.session_state["phase3_summary"] = summary
            st.session_state["phase3_details"] = details_df

        summary = st.session_state.get("phase3_summary")
        details_df = st.session_state.get("phase3_details")

        if summary:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total queries", summary["total_queries"])
            c2.metric("Top-1", summary["top1"])
            c3.metric("Top-3", summary["top3"])
            c4.metric("MRR", summary["mrr"])
            c5.metric("Failures", summary["failures"])

        if details_df is not None and not details_df.empty:
            st.markdown("### Full benchmark results")
            st.dataframe(details_df, width="stretch")

            failures_df = details_df[
                details_df["top3_hit"] == False
            ].copy()  # noqa: E712
            st.markdown("### Failures")
            if failures_df.empty:
                st.success("No top-3 failures in the current benchmark.")
            else:
                st.dataframe(failures_df, width="stretch")
