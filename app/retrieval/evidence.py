from __future__ import annotations

import pandas as pd


def build_evidence(row: pd.Series) -> str:
    bits: list[str] = []
    exact_bonus = float(row.get("exact_bonus", 0.0) or 0.0)
    deity_bonus = float(row.get("deity_bonus", 0.0) or 0.0)
    formula_type_bonus = float(row.get("formula_type_bonus", 0.0) or 0.0)
    formula_slot_bonus = float(row.get("formula_slot_bonus", 0.0) or 0.0)
    offering_overlap = float(row.get("offering_overlap", 0.0) or 0.0)
    recipient_bonus = float(row.get("recipient_bonus", 0.0) or 0.0)
    reading_order_overlap = float(row.get("reading_order_overlap", 0.0) or 0.0)
    aesthetic_flag = bool(row.get("aesthetic_arrangement_flag_bool", False) or False)
    fuzzy_score = float(row.get("fuzzy_score", 0.0) or 0.0)
    tfidf_score = float(row.get("tfidf_score", 0.0) or 0.0)
    overlap_score = float(row.get("overlap_score", 0.0) or 0.0)
    if exact_bonus == 1.0:
        bits.append("matched by exact normalized MdC")
    context_bits: list[str] = []
    if formula_type_bonus > 0.0:
        context_bits.append("formula type")
    if formula_slot_bonus > 0.0:
        context_bits.append("formula slot")
    if deity_bonus > 0.0:
        context_bits.append("deity")
    if recipient_bonus > 0.0:
        context_bits.append("recipient")
    if offering_overlap > 0.0:
        context_bits.append(f"offering items ({offering_overlap:.2f})")
    if context_bits:
        bits.append("context match: " + ", ".join(context_bits))
    else:
        bits.append("context match: none detected")
    if reading_order_overlap > 0.0:
        bits.append(f"reading order contributed ({reading_order_overlap:.2f})")
    else:
        bits.append("reading order did not contribute")
    if aesthetic_flag:
        bits.append("candidate has aesthetic arrangement flag")
    bits.append(f"text similarity: fuzzy={fuzzy_score:.2f}")
    bits.append(f"tfidf={tfidf_score:.2f}")
    bits.append(f"token overlap={overlap_score:.2f}")
    return " | ".join(bits)
