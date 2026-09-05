"""The St Andrews importer: the mapping table, the "lite" transliteration format,
the RES→Unicode conversion, and the shape of the private CSV it writes.

Every sample below is copied verbatim out of the archive (file and line noted) so the
tests pin the parser against real content, not invented examples — but no test reads
`data/raw/standrews/`, which is gitignored and absent on a fresh clone. The RES test
skips when `hieropy` is not installed, because it is an import-time dependency of this
one script and not of the app.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.loader import REQUIRED_COLUMNS  # noqa: E402
from app.data.normalizer import search_fold  # noqa: E402
from scripts.import_standrews import (  # noqa: E402
    SOURCE,
    Block,
    TextEntry,
    _line_display,
    _split_on_suffix_marker,
    content_id,
    convert_word,
    is_hieroglyphic_resource,
    load_res_converter,
    pair_by_name,
    parse_lite_file,
    parse_pieces,
    read_lite_header,
    split_lite_blocks,
    strip_markup,
    to_schema,
)

# resources/urkIV-001Tr.txt, the first three body blocks, verbatim. `<1>` and `<2>`
# are coordinate labels; `<@6>` is a positional anchor for aligning transliteration
# witnesses to each other, not a line label; `^` prefixes a proper name.
URK_IV_1_SAMPLE = """creator = Mark-Jan Nederhof
name = Nederhof
labelname = Ne
language = eng

Transliteration and translation for &quot;The Autobiography of Ahmose
son of Abana&quot;.

###

<1> Hrj-Xnyt ^jaH-msjw sA ^jbAnA mAa-xrw
;
<1> Naval commander Ahmose, son of Abana, justified,

<2> Dd=f
;
<2> says:

<@6>Dd=j n=Tn rmT nbt
;
&quot;I speak to you, all people.
"""


# --- the character table -------------------------------------------------------


def test_ascii_letters_map_to_the_tla_convention() -> None:
    assert convert_word("AaHxXSTD") == "ꜣꜥḥḫẖšṯḏ"


def test_the_yod_is_j_here_not_i_as_in_ramses() -> None:
    """Nederhof writes the yod `j` (9,432 occurrences against 7 bare `i`); the Ramses
    corpus writes it `i`. Both spellings are the same letter and map to `ꞽ`, so the
    two importers cannot disagree about what `Dd=j` and `Dd=i` are."""
    assert convert_word("Dd=j") == "ḏd=ꞽ"
    assert convert_word("Dd=i") == "ḏd=ꞽ"


def test_letters_the_corpus_already_spells_the_same_pass_through() -> None:
    # `y` is the doubled yod and `z` the single Hannig `z` in the whole archive —
    # neither is folded, because folding `z` to `s` would invent a distinction
    # Hannig does not make.
    assert convert_word("qkgtdbpfmnrhswyz") == "qkgtdbpfmnrhswyz"


def test_editorial_apparatus_survives_the_mapping() -> None:
    # `{}` superfluous, `[]` restored, `()` supplied — `normalize_mdc` drops all
    # three on both sides of the search, so they are kept as written here.
    assert convert_word("gm{m}t=s") == "gm{m}t=s"
    assert convert_word("mx[tbt]") == "mḫ[tbt]"


# --- the lite format -----------------------------------------------------------


def test_a_body_block_is_one_containing_a_bare_semicolon() -> None:
    """The header, the prose and the bibliography are separated by blank lines just
    like the body, and the `###` rules that divide them are missing from some files;
    the lone `;` between transliteration and translation is the only reliable mark."""
    blocks = split_lite_blocks(URK_IV_1_SAMPLE)
    assert len(blocks) == 3
    assert all(";" in block for block in blocks)


def test_the_header_stops_at_the_first_blank_line() -> None:
    header = read_lite_header(URK_IV_1_SAMPLE)
    assert header["creator"] == "Mark-Jan Nederhof"
    assert header["name"] == "Nederhof"
    assert "Transliteration" not in " ".join(header)


def test_three_body_blocks_parse_into_three_rows_with_their_translations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sample.txt"
    path.write_text(URK_IV_1_SAMPLE, encoding="utf-8")
    header, blocks = parse_lite_file(path)

    assert header["labelname"] == "Ne"
    assert len(blocks) == 3
    readings = [" ".join(piece.text for piece in block.pieces) for block in blocks]
    assert readings == [
        "Hrj-Xnyt jaH-msjw sA jbAnA mAa-xrw",
        "Dd =f",
        "Dd =j n =Tn rmT nbt",
    ]
    # `&quot;` survives as a quote, not as a marker; the entity is unescaped after
    # the markers are stripped so an escaped `&lt;` could never be read as one.
    assert blocks[2].translation.startswith('"I speak to you')


def test_coordinate_labels_are_carried_and_anchors_are_not(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text(URK_IV_1_SAMPLE, encoding="utf-8")
    _, blocks = parse_lite_file(path)
    assert blocks[0].line_labels == ["1"]
    assert blocks[1].line_labels == ["2"]
    # `<@6>` is an anchor: the block stays on line 2, which is where it is printed.
    assert blocks[2].line_labels == ["2"]


def test_a_label_inside_a_word_marks_the_pieces_as_glued() -> None:
    """`xft-Hr<3>-n` (urkIV-001Tr) is one word the printed edition broke over two
    lines. The pieces must be rejoined into his word, and the break recorded, because
    a reading that owns signs from two lines cannot be pair-aligned."""
    pieces, label = parse_pieces("xft-Hr<3>-n tA r-Dr=f", "2")
    assert [piece.text for piece in pieces] == ["xft-Hr", "-n", "tA", "r-Dr", "=f"]
    assert [piece.line_label for piece in pieces] == ["2", "3", "3", "3", "3"]
    assert [piece.glued for piece in pieces] == [False, True, False, False, False]
    assert label == "3"


def test_a_label_between_words_does_not_glue() -> None:
    pieces, _ = parse_pieces("nn Htm <4> m tA pn Dt", "3")
    assert not any(piece.glued for piece in pieces)
    assert [piece.line_label for piece in pieces][:2] == ["3", "3"]


def test_suffix_pronouns_become_their_own_token() -> None:
    """The corpus writes `ḏd =f` as two tokens and `search_fold` splits on `=` for
    exactly that reason; Nederhof writes it closed up. Only whitespace is added."""
    assert _split_on_suffix_marker("Dd=f") == ["Dd", "=f"]
    assert _split_on_suffix_marker("n=Tn") == ["n", "=Tn"]
    assert _split_on_suffix_marker("jr.n=j") == ["jr.n", "=j"]
    assert _split_on_suffix_marker("sDm") == ["sDm"]
    assert search_fold("ḏd =f") == search_fold("ḏd=f")


def test_notes_leave_the_reading_and_are_kept() -> None:
    # EbersTr.txt line 78: `xpr=s{j} m Hsbt<note>Written <al>Hbt</al>.</note>`
    text, notes = strip_markup("xpr=s{j} m Hsbt<note>Written <al>Hbt</al>.</note>")
    assert text == "xpr=s{j} m Hsbt"
    assert notes == ["Written Hbt."]


def test_no_elements_are_dropped_with_their_contents() -> None:
    # urkIV-013Tr.txt line 44: `<3> txj Abd 4 <no>""</no> sw 9 <no>""</no>` — the
    # ditto marks are a printing convention in a list of dates, not a reading.
    text, _ = strip_markup('<3> txj Abd 4 <no>""</no> sw 9 <no>""</no>')
    assert '"' not in text
    assert text.split() == ["<3>", "txj", "Abd", "4", "sw", "9"]


def test_the_proper_name_marker_is_markup_not_a_letter() -> None:
    pieces, _ = parse_pieces("^sqnj.n-^ra mAa-xrw", "1")
    assert [piece.text for piece in pieces] == ["sqnj.n-ra", "mAa-xrw"]


# --- RES → Unicode -------------------------------------------------------------


def test_res_converts_to_unicode_signs_with_format_controls() -> None:
    """Smoke test on the RES of urkIV-001 line 2 (resources/urkIV-001Hi.xml), the
    line the expert trial used. `insert[s](I10,D46)` is the `ḏd` quadrat."""
    parser, converter = load_res_converter()
    if parser is None:
        pytest.skip("hieropy is not installed")
    fragment = parser.parse("[hlr]insert[s](I10,D46)-[sep=0.5]I9-N35")
    groups = [str(converter.convert_group(g)) for g in fragment.hiero.groups]
    assert len(groups) == 3
    assert groups[0].startswith("𓆓")  # I10, ḏ
    assert "𓂧" in groups[0]  # D46, d
    assert groups[1] == "𓆑"  # I9, f
    assert groups[2] == "𓈖"  # N35, n
    assert not converter.errors


# --- the produced rows ---------------------------------------------------------


def _entry() -> TextEntry:
    return TextEntry(
        name="urkIV-001",
        title="Ahmose son of Abana, Autobiography of",
        path=Path("texts/urkIV-001.xml"),
        collections=["Urkunden der 18. Dynastie 1"],
        translit_paths=[],
        hiero_paths=[Path("resources/urkIV-001Hi.xml")],
        autoalign={},
    )


def _row() -> dict:
    block = Block(index=3, pieces=[], translation="I speak to you.", notes=[])
    return to_schema(
        _entry(),
        "urkIV-001Tr",
        "Nederhof",
        block,
        "ḏd =ꞽ n =ṯn rmṯ nbt",
        "",
        "I speak to you.",
        True,
    )


def test_a_row_has_exactly_the_required_columns() -> None:
    assert list(_row()) == REQUIRED_COLUMNS


def test_the_source_is_always_standrews() -> None:
    """`load_private_examples` refuses a private row with no source, and the app
    picks the CC BY-NC-SA credit line by this exact string."""
    assert SOURCE == "StAndrews"
    assert _row()["source"] == SOURCE


def test_the_source_ref_carries_his_citation_url() -> None:
    ref = _row()["source_ref"]
    assert ref.startswith("https://mjn.host.cs.st-andrews.ac.uk/egyptian/texts/")
    assert "urkIV-001" in ref


def test_stage_genre_and_period_are_left_empty() -> None:
    """Nothing in the archive declares them; an empty column is honest and a guessed
    one is not (and `--stage declared` would read it)."""
    row = _row()
    assert row["language_stage"] == ""
    assert row["genre"] == ""
    assert row["period"] == ""


def test_the_hieroglyphs_column_is_never_filled() -> None:
    """RES's top level is the quadrat, not the word, so no token-for-token sign /
    reading pairing is derivable — and `hieroglyphs` is the column the reading model
    and the sign index pair token-for-token. See the module docstring."""
    assert _row()["hieroglyphs"] == ""


def test_the_content_id_is_stable_and_prefixed() -> None:
    first = content_id("urkIV-001", "urkIV-001Tr", 3, "ḏd =ꞽ n =ṯn rmṯ nbt")
    again = content_id("urkIV-001", "urkIV-001Tr", 3, "ḏd =ꞽ n =ṯn rmṯ nbt")
    other = content_id("urkIV-001", "urkIV-001Tr", 4, "ḏd =ꞽ n =ṯn rmṯ nbt")
    assert first == again
    assert first != other
    assert first.startswith("STANDREWS_")


# --- the display-only line rendering -------------------------------------------


def _block(labels: list[str], index: int = 1) -> Block:
    pieces, _ = parse_pieces(" ".join(f"<{label}> w" for label in labels), "")
    return Block(index=index, pieces=pieces, translation="", notes=[])


def test_line_glyphs_are_shown_only_when_the_block_is_the_whole_line() -> None:
    block = _block(["7"])
    groups = {"7": ["𓅱"]}
    pieces_by_line = {"7": list(block.pieces)}
    assert _line_display(block, groups, pieces_by_line, False) == "𓅱"


def test_line_glyphs_are_withheld_when_another_block_shares_the_line() -> None:
    block = _block(["7"])
    groups = {"7": ["𓅱", "𓈖"]}
    # The line holds one more reading than this block accounts for, so the glyphs
    # are not this sentence's glyphs.
    pieces_by_line = {"7": list(block.pieces) + list(_block(["7"], 2).pieces)}
    assert _line_display(block, groups, pieces_by_line, False) == ""


def test_line_glyphs_are_withheld_across_a_line_break_and_on_damage() -> None:
    block = _block(["7", "8"])
    pieces_by_line = {
        "7": [block.pieces[0]],
        "8": [block.pieces[1]],
    }
    assert _line_display(block, {"7": ["𓅱"], "8": ["𓈖"]}, pieces_by_line, False) == ""

    single = _block(["7"])
    # An empty slot is RES damage notation: a position with no indexable glyph.
    assert _line_display(single, {"7": [""]}, {"7": list(single.pieces)}, False) == ""


# --- resource pairing ----------------------------------------------------------


def test_witnesses_pair_with_their_own_manuscript_only() -> None:
    entry = TextEntry(
        name="Peasant",
        title="Peasant",
        path=Path("texts/Peasant.xml"),
        collections=[],
        translit_paths=[],
        hiero_paths=[
            Path("resources/PeasantHiR.xml"),
            Path("resources/PeasantHiB1.xml"),
        ],
        autoalign={},
    )
    assert pair_by_name(entry, Path("resources/PeasantTrB1.txt")) == Path(
        "resources/PeasantHiB1.xml"
    )
    # `ShipwreckedTrNld` is the Dutch translation witness: no `Hi` of its own, and
    # "the text has exactly one Hi file" must never be enough to pair them.
    assert pair_by_name(entry, Path("resources/PeasantTrB2.txt")) is None


def test_a_non_hieroglyphic_xml_resource_is_not_mistaken_for_one(
    tmp_path: Path,
) -> None:
    """`ShipwreckedOrtho.xml`, `WestcarOrtho.xml`, `PeasantEq*.xml` and the `Im`
    image files are `.xml` with no glyphs; `PtahhotepDevaudP.txt` is a
    transliteration with no `Tr` in its name. Detection is by content."""
    ortho = tmp_path / "ShipwreckedOrtho.xml"
    ortho.write_text('<?xml version="1.0"?><orthography/>', encoding="utf-8")
    hiero = tmp_path / "ShipwreckedHi.xml"
    hiero.write_text(
        '<?xml version="1.0"?><egyptian><segment><texthi>N35</texthi></segment>'
        "</egyptian>",
        encoding="utf-8",
    )
    assert not is_hieroglyphic_resource(ortho)
    assert is_hieroglyphic_resource(hiero)
    assert not is_hieroglyphic_resource(tmp_path / "PtahhotepDevaudP.txt")
