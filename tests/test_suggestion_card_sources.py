"""Hieroglyphs and a real source on every suggestion card (Camilla, 2026-10-25).

A card used to list `BBAW/bbaw_egyptian_2018/B004065` — an internal label — and no
glyphs. It now shows the exact row the reading came from (its glyphs, or "no
hieroglyphs recorded in this source") and that row's source as a citation: ORAEC
text metadata for AES and accepted-link BBAW rows, a keyed session's St Andrews
text/witness/line, and "source text not recorded in this corpus" for everything
else. These tests pin each point of the spec (docs: the lead's camilla-cards-spec):
the NC gate, escaping, `<g>` codes, blank-line-free HTML, three real rows, and an
unchanged ranking.
"""

from __future__ import annotations

import hashlib
import html
import random
import re
from pathlib import Path

import pandas as pd
import pytest

from app.data.loader import REQUIRED_COLUMNS, load_private_examples
from app.data.source_metadata import (
    LINE_NOT_RECORDED,
    NOT_RECORDED,
    Citation,
    SourceCitations,
    TextCitation,
    build_private_citations,
    build_source_citations,
    citation_for,
    load_bbaw_links,
    load_text_citations,
    parse_standrews_citation,
)
from app.services.suggestions import ReadingSuggestion, SupportingExample, suggest_top_readings
from app.ui.source_display import (
    NO_GLYPHS,
    citation_html,
    example_block_html,
    examples_html,
    glyphs_html,
    sign_reference,
)
from tests.test_audit_services import _random_pool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_CSV = PROJECT_ROOT / "data" / "processed" / "examples.csv"

METADATA_COLUMNS = [
    "oraec_id", "aed_text_id", "title", "hierarchical_path", "date", "origplace",
    "objecttype", "location", "idno", "bibliography", "text_authors", "text_licence",
    "text_provenance", "trismegistos_id", "trismegistos_url", "trismegistos_licence",
    "trismegistos_provenance", "aes_rows_linked", "bbaw_rows_linked", "retrieved",
]
LINK_COLUMNS = [
    "source", "source_sentence_id", "oraec_id", "match_method", "key_words",
    "translation_match", "link_status",
]
METHOD = "unique sentence dedup_key + translation"


def _text(html_fragment: str) -> str:
    """The visible text of an HTML fragment, one line per block element."""
    spaced = re.sub(r"</div>|<summary>|</summary>", "\n", html_fragment)
    return "\n".join(
        line.strip()
        for line in html.unescape(re.sub(r"<[^>]+>", "", spaced)).splitlines()
        if line.strip()
    )


def _metadata_dir(tmp_path: Path, texts: list[dict], links: list[dict]) -> Path:
    rows = [{**{c: "" for c in METADATA_COLUMNS}, **t} for t in texts]
    pd.DataFrame(rows, columns=METADATA_COLUMNS).to_csv(tmp_path / "source_metadata_oraec.csv", index=False)
    pd.DataFrame(links, columns=LINK_COLUMNS).to_csv(
        tmp_path / "source_metadata_oraec_bbaw_links.csv", index=False
    )
    return tmp_path


def _link(sentence: str, oraec: str, **over) -> dict:
    row = {
        "source": "BBAW", "source_sentence_id": sentence, "oraec_id": oraec,
        "match_method": METHOD, "key_words": "5", "translation_match": "True",
        "link_status": "accepted",
    }
    row.update(over)
    return row


def _public(rows: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows, columns=["source", "source_text_id", "source_sentence_id", "source_ref"]
    )


# ---------- 1/2: the exact supporting row, carried on the suggestion ----------


def _pool_with_a_glyphless_best() -> pd.DataFrame:
    base = {"translation": "x", "hieroglyphs_norm": "", "source_ref": "", "grammar_notes": ""}
    return pd.DataFrame(
        [
            # The best-scoring row of the group has no glyphs; a lower one has some.
            {**base, "transliteration_gold": "ḥtp", "final_score": 0.9, "hieroglyphs": "",
             "source": "BBAW", "source_text_id": "bbaw_egyptian_2018", "source_sentence_id": "B1"},
            {**base, "transliteration_gold": "ḥtp", "final_score": 0.5, "hieroglyphs": "𓊵𓏏𓊪",
             "hieroglyphs_norm": "𓊵𓏏𓊪", "translation": "y",
             "source": "AES", "source_text_id": "AES_X", "source_sentence_id": "S2"},
        ]
    )


def test_the_card_shows_exactly_the_row_the_reading_came_from_never_a_prettier_one():
    (suggestion,) = suggest_top_readings(_pool_with_a_glyphless_best(), "ḥtp")
    best, other = suggestion.supporting_examples
    assert best.key == ("BBAW", "bbaw_egyptian_2018", "B1")
    assert other.key == ("AES", "AES_X", "S2")
    rendered = examples_html(suggestion.supporting_examples, [Citation("none")] * 2)
    first, _, folded = rendered.partition("<details")
    assert NO_GLYPHS in first and "𓊵𓏏𓊪" not in first
    assert "1 more attestation" in folded and "𓊵𓏏𓊪" in folded


def test_supporting_examples_match_supporting_sources_and_ranking_is_unchanged():
    """A fixed random sample, fingerprinted on the code before this change: the
    readings, confidences, counts, source labels and evidence lines are identical."""
    rng = random.Random(20261025)
    digest = hashlib.sha256()
    for _ in range(300):
        frame, kwargs = _random_pool(rng)
        for s in suggest_top_readings(frame, **kwargs):
            digest.update(
                repr(
                    (
                        s.candidate_transliteration,
                        s.confidence_score,
                        s.supporting_example_count,
                        tuple(s.supporting_sources),
                        s.evidence_summary,
                    )
                ).encode()
            )
            assert 1 <= len(s.supporting_examples) <= 5
            assert [
                f"{e.source}/{e.source_text_id}/{e.source_sentence_id}"
                for e in s.supporting_examples
            ] == s.supporting_sources
    assert digest.hexdigest() == (
        "455d59ac7fcc779200df5046cc5a5ed503f2593285188647911f96e7ce616803"
    )


def test_a_suggestion_built_without_examples_still_constructs():
    s = ReadingSuggestion("x", 0.5, 1, ["a/b/c"], "e")
    assert s.supporting_examples == ()


# ---------- 3: the join ----------


def test_aes_joins_by_the_text_id_in_source_ref_and_bbaw_only_through_accepted_links(tmp_path):
    directory = _metadata_dir(
        tmp_path,
        [
            {"oraec_id": "oraec1", "aed_text_id": "AEDTEXT1", "title": "Text one"},
            {"oraec_id": "oraec2", "aed_text_id": "AEDTEXT2", "title": "Text two"},
        ],
        [
            _link("B1", "oraec2"),
            _link("B2", "oraec2", key_words="2"),             # short key
            _link("B3", "oraec2", translation_match="False"),  # translation differs
            _link("B4", "oraec2", link_status="candidate"),    # not accepted
            _link("B5", "oraec1"), _link("B5", "oraec2"),      # conflicting duplicate
            _link("B6", "oraec999"),                           # unknown text
            _link("B7", "oraec2", match_method="fuzzy"),       # another rule
        ],
    )
    # The candidates file is never read: a "link" there must not cite anything.
    pd.DataFrame([_link("B8", "oraec2")], columns=LINK_COLUMNS).to_csv(
        directory / "source_metadata_oraec_bbaw_link_candidates.csv", index=False
    )
    public = _public(
        [
            ("AES", "AES_1", "S1", "AES/x#text=AEDTEXT1&sentence=abc"),
            ("AES", "AES_9", "S9", "AES/x#text=NOSUCHTEXT&sentence=abc"),
            *[("BBAW", "bbaw_egyptian_2018", f"B{n}", "phiwi/bbaw_egyptian") for n in range(1, 9)],
            ("Ramses", "RAMSES_1", "S_train_000001", "ramses-trl 2019-09-01 train line 1"),
        ]
    )
    index = build_source_citations(public, directory)
    assert set(index.by_key) == {("AES", "AES_1", "S1"), ("BBAW", "bbaw_egyptian_2018", "B1")}
    assert index.by_key[("AES", "AES_1", "S1")].title == "Text one"
    assert index.by_key[("BBAW", "bbaw_egyptian_2018", "B1")].title == "Text two"


def test_missing_metadata_gives_the_honest_line_not_an_error(tmp_path):
    public = _public([("AES", "AES_1", "S1", "AES/x#text=AEDTEXT1&sentence=abc")])
    index = build_source_citations(public, tmp_path)
    example = SupportingExample("AES", "AES_1", "S1")
    assert citation_for(example, index) == Citation("none")


# ---------- 4: cleaning at load ----------


def test_metadata_is_cleaned_once_at_load(tmp_path):
    long_entry = "- " + " ".join(["Author, A long bibliography entry"] * 12)
    directory = _metadata_dir(
        tmp_path,
        [
            {
                "oraec_id": "oraec1",
                "aed_text_id": "T1",
                "title": "Papyrus &quot;Schmitt&quot;\n\n(pBerlin)",
                "bibliography": f"\n{long_entry}\n- Second entry",
                "location": "21 = Objekttyp",
                "idno": "P &amp; 3057",
                "trismegistos_id": "12a4",
                "text_authors": "Renata &amp; Peter Landgrafova &amp; Dils",
            },
            {"oraec_id": "oraec2", "aed_text_id": "T2", "trismegistos_id": "130723",
             "bibliography": "- Short entry [P]", "text_authors": "Frank Feder"},
        ],
        [],
    )
    texts = load_text_citations(directory / "source_metadata_oraec.csv")
    one, two = texts["oraec1"], texts["oraec2"]
    assert one.title == 'Papyrus "Schmitt" (pBerlin)'
    assert one.location == ""                      # "^\d+ = " placeholder dropped
    assert one.idno == "P & 3057"
    assert one.tm_id == "" and one.tm_url == ""    # not all digits: no link at all
    assert one.authors == ""                       # garbled join: generic credit instead
    assert len(one.bib_short) <= 160 and one.bib_short.endswith("…")
    assert one.bib_short.startswith("Author, A long")
    assert two.bib_short == "Short entry [P]"
    assert two.tm_url == "https://www.trismegistos.org/text/130723"
    rendered = citation_html(Citation("oraec", text=one))
    # Decoded at load, escaped once at render: never double-encoded.
    assert "&amp;quot;" not in rendered and "&quot;Schmitt&quot;" in rendered
    assert "AED authors" in rendered and "Landgrafova" not in rendered
    assert "bibliography not recorded" not in rendered
    assert "Trismegistos link not recorded" in rendered


# ---------- escaping ----------


def test_quotes_and_script_tags_in_the_bibliography_never_become_markup(tmp_path):
    directory = _metadata_dir(
        tmp_path,
        [
            {
                "oraec_id": "oraec1",
                "aed_text_id": "T1",
                "title": '<img src=x onerror="alert(1)">',
                "bibliography": '- "Quoted" </script><script>alert(1)</script> \'single\'',
                "location": '"><b>bold</b>',
                "idno": "&lt;script&gt;",
                "date": "</div><div>",
                "trismegistos_id": '1" onclick="x',
                "text_authors": '<a href="javascript:x">me</a>',
            }
        ],
        [],
    )
    text = load_text_citations(directory / "source_metadata_oraec.csv")["oraec1"]
    rendered = citation_html(Citation("oraec", text=text))
    lowered = rendered.lower()
    for bad in ("<script", "</script", "<img", "<b>", '<a href="javascript', "onclick", 'onerror="'):
        assert bad not in lowered, bad
    # The only tags are the template's own.
    assert set(re.findall(r"<([a-z]+)", rendered)) <= {"div", "a"}
    assert rendered.count("<a ") == 2  # the ORAEC and CC BY-SA links; no TM link
    assert "&quot;Quoted&quot;" in rendered
    # Every href is one of the fixed, trusted URLs.
    for href in re.findall(r'href="([^"]*)"', rendered):
        assert href.startswith("https://"), href


def test_a_hostile_glyph_string_stays_text_and_the_code_tooltip_stays_an_attribute():
    raw = '𓀀<script>x</script><g>"onmouseover=alert(1) x="</g><b>𓁷</b>'
    rendered = glyphs_html(raw, {})
    assert "<script" not in rendered and "<b>" not in rendered
    assert "&lt;script&gt;" in rendered and "&lt;b&gt;" in rendered
    (title,) = re.findall(r'title="([^"]*)"', rendered)
    assert "onmouseover" in html.unescape(title)
    assert rendered.count("<span") == 1
    assert "onmouseover=alert" not in rendered.replace(title, "")


# ---------- 5: <g> codes ----------


def test_sign_codes_render_as_one_marked_box_each_with_an_honest_tooltip():
    signs = sign_reference()
    rendered = glyphs_html("𓎟<g>Ff1</g> <g><g>US9No2VARA</g></g> <g>NUM4</g> <g>2</g>", signs)
    assert "<g>" not in rendered and "&lt;g&gt;" not in rendered
    boxes = re.findall(r'<span class="glyph-missing"[^>]*title="([^"]*)"', rendered)
    assert len(boxes) == 4
    ff1, nested, num4, two = (html.unescape(b) for b in boxes)
    assert ff1.startswith("Sign code Ff1, not encoded as a Unicode sign in this source.")
    assert "Unikemet 18 lists Ff1 as U+133F9: A curved diagonal stroke." in ff1
    assert "US9No2VARA" in nested and "Unikemet" not in nested  # unknown: nothing invented
    assert "numeral" in num4 and "numeral" in two
    # The code is never swapped for the character Unikemet lists.
    assert "\U000133f9" not in rendered
    assert rendered.startswith('<div class="suggestion-glyphs">𓎟<span')


def test_no_glyphs_says_so_explicitly():
    for raw in ("", "  ", None):
        assert glyphs_html(raw) == f'<div class="no-glyphs">{NO_GLYPHS}</div>'


# ---------- 6: St Andrews ----------


def _standrews_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "private"
    directory.mkdir()
    rows = []
    for n, where in enumerate(["line 7", "block 4", "line 3,11, 3,12"]):
        row = {c: "" for c in REQUIRED_COLUMNS}
        row.update(
            source="StAndrews",
            source_text_id=f"STANDREWS_GATE{n}",
            source_sentence_id=f"S_urkGATE-001_GateWitnessTr_{n:04d}",
            transliteration_gold="zzqqwx nfr",
            source_ref=(
                "https://mjn.host.cs.st-andrews.ac.uk/egyptian/texts/ "
                f"urkGATE-001 (GateWitnessTr) {where}"
            ),
            grammar_notes=(
                "St Andrews corpus, Hannig conventions. Witness: Gatewitness. "
                "Follows Gate Edition 1; Gate Edition 1; Gate Edition 2."
            ),
        )
        rows.append(row)
    pd.DataFrame(rows).to_csv(directory / "standrews.csv", index=False)
    return directory


def test_standrews_citation_parses_text_witness_line_and_never_relabels_a_block(tmp_path):
    private = build_private_citations(load_private_examples(_standrews_dir(tmp_path)))
    lines = sorted(c.line for c in private.values())
    assert lines == sorted(["line 7", LINE_NOT_RECORDED, "line 3,11, 3,12"])
    one = next(iter(private.values()))
    assert (one.text, one.witness, one.witness_name) == ("urkGATE-001", "GateWitnessTr", "Gatewitness")
    assert one.edition == "Gate Edition 1; Gate Edition 2"
    assert parse_standrews_citation("ramses-trl 2019-09-01 train line 4") is None


def test_an_unkeyed_render_never_sees_a_standrews_citation(tmp_path):
    private = build_private_citations(load_private_examples(_standrews_dir(tmp_path)))
    key = next(k for k, c in private.items() if c.line == "line 7")
    example = SupportingExample(*key)
    # Even with the private index in hand, a session that fails the check gets nothing.
    for allowed, index in ((False, private), (False, None), (True, None)):
        citation = citation_for(example, SourceCitations({}), index, allowed)
        rendered = example_block_html(example, citation)
        assert citation == Citation("none")
        for tracer in ("urkGATE", "GateWitness", "Gatewitness", "Gate Edition", "by-nc-sa", "St Andrews"):
            assert tracer not in rendered, tracer
        assert NOT_RECORDED in rendered
    keyed = example_block_html(example, citation_for(example, SourceCitations({}), private, True))
    assert "text urkGATE-001, witness GateWitnessTr (Gatewitness), line 7" in _text(keyed)
    assert "by-nc-sa" in keyed


# ---------- 7: never an internal reference ----------


BANNED = ("parquet", "#row=", "train line", "ramses-trl", "phiwi/", "AES_", "RAMSES_", "bbaw_egyptian")


@pytest.fixture(scope="module")
def real_rows() -> pd.DataFrame:
    return pd.read_csv(
        EXAMPLES_CSV,
        usecols=["source", "source_text_id", "source_sentence_id", "hieroglyphs", "source_ref",
                 "grammar_notes"],
        dtype=str,
        keep_default_na=False,
    )


@pytest.fixture(scope="module")
def real_index(real_rows) -> SourceCitations:
    return build_source_citations(real_rows)


def test_no_card_ever_shows_an_internal_reference(real_rows, real_index):
    sample = pd.concat(
        group.sample(min(len(group), 1500), random_state=7)
        for _, group in real_rows.groupby("source")
    )
    for _, row in sample.iterrows():
        example = SupportingExample.from_row(row)
        rendered = citation_html(citation_for(example, real_index), example.source)
        for banned in BANNED:
            assert banned not in rendered, (row["source_sentence_id"], banned)
    assert len(real_index) == 9823 + 41475
    assert real_index.text_count <= 7873


# ---------- 10: three real rows ----------

AES_EXPECTED = """\
𓃹𓈖𓇋𓈖 𓅐𓏏𓁐 𓆑 𓁷𓏤 𓎛𓎛𓂻 𓆑 𓅓𓆓𓏏𓏤𓆑𓄡𓏏𓏤𓆑 𓅓 𓇏𓏏𓈇𓏫 𓏏𓈖
Mythologisches Handbuch für Unterägyptische Gaue / pBrooklyn 47.218.84 ("Mythes et Légendes du Delta")
The Brooklyn Museum · Inv./designation: 47.218.84 · Psammetich I.
D. Meeks, Mythes et Légendes du Delta d'après le papyrus Brooklyn 47.218.84, MIFAO 125 (2006) [P,T,Ü,K].
Trismegistos TM 111740 ↗
Text metadata: ORAEC (Frank Feder), CC BY-SA 4.0 · Trismegistos id: CC0 1.0"""

BBAW_EXPECTED = """\
𓃹𓈖𓇋𓈖 𓅯𓄿 𓂝𓆓𓂧𓏲𓀔𓅪𓀀 𓁷𓏤 𓌃𓂧𓏲𓀁𓏫 𓅓𓂞 𓅯𓄿𓇋𓇋 𓆑 𓌢𓀀 𓉻𓏛 𓅓𓆓𓂧
Recto: Das Zweibrüdermärchen / pD'Orbiney = pBM EA 10183
British Museum · Inv./designation: pD'Orbiney · Amenmesse | Sethos II.
A.H. Gardiner, Late-Egyptian Stories; Bruxelles 1981 (Reprint von 1932) (BiAe 1); S. IX-X, 9-30 [*K,*T]
Trismegistos TM 381214 ↗
Linked to this text by sentence match; line not recorded.
Text metadata: ORAEC (Lutz Popko), CC BY-SA 4.0 · Trismegistos id: CC0 1.0"""

RAMSES_EXPECTED = """\
𓁹𓏲𓇋𓇋 𓏲𓏫 𓋹 𓈖 𓎟
source text not recorded in this corpus"""


@pytest.mark.parametrize(
    "sentence_id, expected, boxes, href",
    [
        ("S23DC1CE003E9", AES_EXPECTED, 0, "https://www.trismegistos.org/text/111740"),
        ("B009423", BBAW_EXPECTED, 2, "https://www.trismegistos.org/text/381214"),
        ("S_train_000048", RAMSES_EXPECTED, 4, None),
    ],
    ids=["AES", "BBAW-linked", "Ramses"],
)
def test_three_real_rows_render_as_expected(real_rows, real_index, sentence_id, expected, boxes, href):
    row = real_rows[real_rows["source_sentence_id"] == sentence_id].iloc[0]
    example = SupportingExample.from_row(row)
    rendered = example_block_html(example, citation_for(example, real_index), sign_reference())
    assert _text(rendered).replace("\xa0", " ") == expected
    assert rendered.count('class="glyph-missing"') == boxes
    hrefs = re.findall(r'href="(https://www\.trismegistos[^"]*)"', rendered)
    assert hrefs == ([href] if href else [])


# ---------- the card itself ----------


@pytest.fixture(scope="module")
def app_module():
    import app.ui.whyptology_app as w

    return w


def test_the_card_html_has_no_blank_line_even_with_blank_lines_in_the_metadata(tmp_path, app_module):
    directory = _metadata_dir(
        tmp_path,
        [{"oraec_id": "oraec1", "aed_text_id": "T1", "title": "A\n\n\nB",
          "bibliography": "\n\n- First\n\n\n- Second\n\n", "date": "x\n\ny"}],
        [],
    )
    index = build_source_citations(
        _public([("AES", "AES_1", "S1", "AES/x#text=T1&sentence=s")]), directory
    )
    examples = (
        SupportingExample("AES", "AES_1", "S1", "𓀀\n\n<g>Ff1</g>\n\n𓁷"),
        SupportingExample("Ramses", "RAMSES_1", "S_train_1", ""),
    )
    suggestion = ReadingSuggestion("ꞽw", 0.5, 2, ["a", "b"], "evidence", examples)
    card = app_module.suggestion_card_html(1, suggestion, index)
    assert card.startswith('<article class="suggestion-card">')
    assert "\n\n" not in card
    assert all(line.strip() for line in card.splitlines())
    assert "suggestion-sources" not in card and "AES_1" not in card
    assert "A B" in card and "First" in card and "1 more attestation" in card


def test_card_citations_check_the_reviewer_gate_on_every_call(tmp_path, monkeypatch, app_module):
    w = app_module
    monkeypatch.setattr(w, "PRIVATE_DATA_DIR", _standrews_dir(tmp_path))
    w.load_private_citations.clear()
    example = SupportingExample(
        "StAndrews", "STANDREWS_GATE0", "S_urkGATE-001_GateWitnessTr_0000"
    )
    suggestion = ReadingSuggestion("zzqqwx nfr", 0.5, 1, ["x"], "e", (example,))
    try:
        monkeypatch.setattr(w, "private_rows_unlocked", lambda: True)
        keyed = w.suggestion_card_html(1, suggestion, *w.card_citation_indexes())
        assert "urkGATE-001" in keyed and "by-nc-sa" in keyed
        # The private cache is warm now; locking must still cut it off.
        monkeypatch.setattr(w, "private_rows_unlocked", lambda: False)
        public, private, allowed = w.card_citation_indexes()
        assert private is None and allowed is False
        unkeyed = w.suggestion_card_html(1, suggestion, public, private, allowed)
        for tracer in ("urkGATE", "GateWitness", "Gate Edition", "by-nc-sa"):
            assert tracer not in unkeyed, tracer
        # The row the reading came from is private: a denied render shows no
        # evidence row at all rather than its glyphs or a stand-in row.
        assert "suggestion-example" not in unkeyed
    finally:
        w.load_private_citations.clear()


# ---------- 8: credits ----------


def test_oraec_and_trismegistos_credits_appear_only_with_aes_or_bbaw(app_module):
    w = app_module
    for sources, shown in ((["AES"], True), (["BBAW", "Ramses"], True), (["Ramses", "TLA"], False)):
        credit = w.corpus_credit_html(pd.DataFrame({"source": sources}))
        assert ("corpus_raw_data" in credit) is shown, sources
        assert ("publicdomain/zero" in credit) is shown, sources
    assert "ORAEC" not in w.CORPUS_CREDITS


def test_the_citation_cache_identity_names_the_metadata_files_and_exclusions(app_module, monkeypatch):
    w = app_module
    before = w.source_citations_revision()
    assert "source_metadata_oraec.csv:" in before
    assert "source_metadata_oraec_bbaw_links.csv:" in before
    monkeypatch.setenv("CORPUS_SOURCES_EXCLUDE", "BBAW")
    assert w.source_citations_revision() != before


# ---------- review follow-up: denied renders, stale caches ----------


PRIVATE_GLYPHS = "𓀀𓁷<g>GATEX9</g>"


def _private_example(n: int = 0) -> SupportingExample:
    return SupportingExample(
        "StAndrews", f"STANDREWS_GATE{n}", f"S_urkGATE-001_GateWitnessTr_{n:04d}", PRIVATE_GLYPHS
    )


def test_a_denied_render_shows_no_private_glyphs_and_no_private_backed_card(app_module):
    w = app_module
    public = SupportingExample("Ramses", "RAMSES_1", "S_train_1", "𓂋𓈖")
    mixed = ReadingSuggestion("ꞽw", 0.5, 2, ["a", "b"], "e", (public, _private_example(1)))
    private_backed = ReadingSuggestion("zzqqwx nfr", 0.5, 1, ["x"], "e", (_private_example(),))
    public_only = ReadingSuggestion("nfr", 0.4, 1, ["p"], "e", (public,))
    # Even when a card is rendered directly, no private glyph reaches it...
    card = w.suggestion_card_html(1, mixed, SourceCitations({}), None, False)
    assert "GATEX9" not in card and "𓀀𓁷" not in card
    assert "𓂋𓈖" in card and "more attestation" not in card
    best_private = w.suggestion_card_html(1, private_backed, SourceCitations({}), None, False)
    assert "GATEX9" not in best_private and "𓀀𓁷" not in best_private
    # ...and a denied render drops every card a private row stands behind.
    cards = [private_backed, mixed, public_only]
    assert w.visible_suggestions(cards, False) == [public_only]
    keyed = w.suggestion_card_html(1, mixed, SourceCitations({}), None, True)
    assert "GATEX9" in keyed
    assert w.visible_suggestions(cards, True) == cards


def test_losing_private_access_any_way_drops_the_keyed_results(app_module, monkeypatch):
    w = app_module
    state = {}
    monkeypatch.setattr(w, "private_rows_unlocked", lambda: True)
    w.enforce_private_session_gate(state)
    # A keyed search stores suggestions built on private rows...
    state["whyptology_suggestions"] = [
        ReadingSuggestion("zzqqwx nfr", 0.5, 1, ["x"], "e", (_private_example(),))
    ]
    state["whyptology_results"] = pd.DataFrame({"hieroglyphs": [PRIVATE_GLYPHS]})
    w.enforce_private_session_gate(state)
    assert "whyptology_suggestions" in state
    # ...then access goes away without the Lock button (key removed from the host).
    monkeypatch.setattr(w, "private_rows_unlocked", lambda: False)
    w.enforce_private_session_gate(state)
    assert "whyptology_suggestions" not in state and "whyptology_results" not in state
    # An unkeyed session's own results are never touched.
    state["whyptology_suggestions"] = ["public"]
    w.enforce_private_session_gate(state)
    assert state["whyptology_suggestions"] == ["public"]


def test_a_changed_private_file_is_reread_not_served_from_the_old_cache(tmp_path, monkeypatch, app_module):
    import os

    w = app_module
    directory = _standrews_dir(tmp_path)
    monkeypatch.setattr(w, "PRIVATE_DATA_DIR", directory)
    monkeypatch.setattr(w, "private_rows_unlocked", lambda: True)
    w.load_private_corpus.clear()
    w.load_private_citations.clear()
    example = SupportingExample("StAndrews", "STANDREWS_GATE0", "S_urkGATE-001_GateWitnessTr_0000")
    try:
        _, private, _ = w.card_citation_indexes()
        assert private[example.key].line == "line 7"
        path = directory / "standrews.csv"
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        frame.loc[0, "source_ref"] = frame.loc[0, "source_ref"].replace("line 7", "line 77")
        frame.to_csv(path, index=False)
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
        _, private, _ = w.card_citation_indexes()
        assert private[example.key].line == "line 77"
        assert w.current_private_corpus()["source_ref"].str.contains("line 77").any()
    finally:
        w.load_private_corpus.clear()
        w.load_private_citations.clear()


def test_source_exclusions_reach_the_cached_public_frame(app_module, monkeypatch):
    w = app_module
    monkeypatch.delenv("CORPUS_SOURCES_EXCLUDE", raising=False)
    assert "BBAW" in set(w.load_corpus_csv()["source"])
    monkeypatch.setenv("CORPUS_SOURCES_EXCLUDE", "BBAW")
    assert "BBAW" not in set(w.load_corpus_csv()["source"])
    public, _, _ = w.card_citation_indexes()
    assert not any(key[0] == "BBAW" for key in public.by_key)


def test_the_word_table_shows_a_sign_code_as_a_plain_label_not_markup(app_module):
    row = pd.Series({"transliteration_gold": "ꞽw nfr", "hieroglyphs": "𓇋𓅱 <g>Ff1</g>𓄤"})
    signs = list(app_module.token_analysis(row)["Sign"])
    assert signs == ["𓇋𓅱", "[code Ff1]𓄤"]
