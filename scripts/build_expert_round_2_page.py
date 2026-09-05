"""Render the expert-round-2 before/after cases as a self-contained review page.

Roadmap item 4 of the plan for 2026-09-06. Five queries where the candidate ordering
change (preset ``cfg_c``: carry retrieval's IDF overlap forward into the re-rank, and
move ``char_similarity``'s weight to ``relative_score``) moves a named suggestion a named
number of ranks. The page shows the tool's top three *before* and *after* the change,
side by side, marks the suggestion that moved, and asks one question per case.

The top-three lists are read from the evaluation result CSVs, so the page is reproducible:
change the run, re-run this, and the page updates. The one thing not in those CSVs is the
exact rank a demoted suggestion falls to (the CSVs record only the top three); those
figures were read from ``scripts/inspect_suggestion_boundary.py`` under the ``default`` and
``cfg_c`` presets and are recorded here as the per-case ``moved`` line, with the preset
named so a pasted figure can never lose its provenance.

Nothing is uploaded. A reviewer's answers live in their browser until they export a CSV;
the export happens entirely in the page. This script sends nothing anywhere either — it
only reads local CSVs and writes one HTML file.

    python scripts/build_expert_round_2_page.py
    python scripts/build_expert_round_2_page.py --output data/benchmarks/expert_round_2.html
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BENCH = PROJECT_ROOT / "data" / "benchmarks"
V4_BEFORE = BENCH / "ceval_v4_v4_app_auto_results.csv"
V4_AFTER = BENCH / "ceval_v4_v4_app_auto_cfg_c.csv"
HOLD_BEFORE = BENCH / "ceval_holdout_v4_app_auto_results.csv"
HOLD_AFTER = BENCH / "ceval_holdout_v4_app_auto_cfg_c.csv"
OUTPUT_PATH = BENCH / "expert_round_2.html"

# Per-case editorial content. Suggestion lists come from the CSVs; everything here is the
# frame around them. ``star_before`` / ``star_after`` are 0-based indices into the top
# three that the change moved (None = nothing marked in that column). ``options`` are the
# two radio labels; ``value`` is the machine token exported for each.
CASES = [
    {
        "id": "COMP_001",
        "before_file": V4_BEFORE,
        "after_file": V4_AFTER,
        "tag": "the change pushes a near-identical sentence off the list",
        "star_before": 0,
        "star_after": None,
        "moved": (
            "The AES row r sḫr.n =ꞽ ḫft.pl nb n.w rꜥw … — almost word-for-word the "
            "sentence the string came from — moves from 1st to off the list entirely "
            "(below 8th) under the change."
        ),
        "question": (
            "The reading the change pushed off the list is nearly the same sentence as "
            "your string; the new 1st suggestion is ḏi̯ =ꞽ sḫr nḥḥ ḫft ⸮ꞽb? =ꞽ. Was the "
            "displaced reading the more useful one to have shown first?"
        ),
        "options": [
            {"value": "displaced_better", "label": "Yes — displaced reading was better"},
            {"value": "new_first_fine", "label": "No — new 1st is fine"},
        ],
    },
    {
        "id": "COMP_007",
        "before_file": V4_BEFORE,
        "after_file": V4_AFTER,
        "tag": "the change lifts a matching parallel from 6th to 1st",
        "star_before": None,
        "star_after": 0,
        "moved": (
            "The TLA row ꞽ:fḫ n =k s(ꞽ) zꜣ =k … — the corpus parallel that shares the "
            "string's rarer word fḫ — moves from 6th to 1st. This is the one case where "
            "the change is a promotion into the top three."
        ),
        "question": (
            "Is the new 1st suggestion ꞽ:fḫ n =k s(ꞽ) zꜣ =k … a reading you would consider "
            "for this string, and more useful than ꜣḫ =ꞽ ꞽm =f, which it displaced?"
        ),
        "options": [
            {"value": "new_first_better", "label": "Yes — new 1st is better"},
            {"value": "old_first_better", "label": "No — old 1st was better"},
        ],
    },
    {
        "id": "COMP_022",
        "before_file": V4_BEFORE,
        "after_file": V4_AFTER,
        "tag": "the change drops an offering-formula parallel out of the top three",
        "star_before": 2,
        "star_after": None,
        "moved": (
            "The offering-formula parallel ꞽni̯.t pr.t-ḫrw ꞽn nʾ.t.pl n.ꞽ.wt moves from "
            "3rd to 7th, so it leaves the top three; wꜣḥ pr-ḫrw ꞽn wt(.ꞽ) takes the 3rd "
            "slot in its place. The top two Ramses rows are unchanged."
        ),
        "question": (
            "For this string, does the offering-formula parallel "
            "ꞽni̯.t pr.t-ḫrw ꞽn nʾ.t.pl n.ꞽ.wt belong in the top three, ahead of "
            "wꜣḥ pr-ḫrw ꞽn wt(.ꞽ)?"
        ),
        "options": [
            {"value": "belongs_top3", "label": "Yes — it belongs in the top three"},
            {"value": "replacement_fine", "label": "No — the replacement is fine"},
        ],
    },
    {
        "id": "HOLD_010",
        "before_file": HOLD_BEFORE,
        "after_file": HOLD_AFTER,
        "tag": "the change drops the parallel with both royal names from 1st",
        "star_before": 0,
        "star_after": None,
        "moved": (
            "The parallel that carries both royal names and mn.t.du, "
            "pri̯.n Nmt.ꞽ-m-zꜣ=f Mr.n-Rꜥw ꞽm.wtꞽ mn.t.du psḏ.t.du, moves from 1st to off "
            "the list entirely (below 8th). Before the change all three suggestions named "
            "the same two kings; after it, only the 2nd does."
        ),
        "question": (
            "Was the displaced parallel with both royal names, "
            "pri̯.n Nmt.ꞽ-m-zꜣ=f Mr.n-Rꜥw ꞽm.wtꞽ mn.t.du psḏ.t.du, the more useful reading "
            "to have shown first, ahead of the new 1st pri̯ =ꞽ ẖr smꞽ nm.t nṯr?"
        ),
        "options": [
            {"value": "displaced_better", "label": "Yes — displaced reading was better"},
            {"value": "new_first_fine", "label": "No — new 1st is fine"},
        ],
    },
    {
        "id": "HOLD_016",
        "before_file": HOLD_BEFORE,
        "after_file": HOLD_AFTER,
        "tag": "the change swaps 1st and 3rd inside the top three",
        "star_before": 0,
        "star_after": 2,
        "moved": (
            "The reading ḫ⸢r⸣-mdꞽ tm ḫꜣꜥ nnw mḏꜣ Ksꞽ mtw =k ḏi̯.t … moves from 1st to 3rd; "
            "mtw =k ⸢tm⸣ nni̯ [⸮Pꜣ-kꜣmn?] [pꜣy] [=ꞽ] sn rises from 2nd to 1st. All three "
            "stay in the top three — only their order changes."
        ),
        "question": (
            "For this string, which reading do you prefer at 1st place — the current "
            "ḫ⸢r⸣-mdꞽ tm ḫꜣꜥ nnw mḏꜣ Ksꞽ mtw =k ḏi̯.t …, or the proposed "
            "mtw =k ⸢tm⸣ nni̯ [⸮Pꜣ-kꜣmn?] [pꜣy] [=ꞽ] sn?"
        ),
        "options": [
            {"value": "keep_current", "label": "Keep current 1st"},
            {"value": "adopt_proposed", "label": "Adopt proposed 1st"},
        ],
    },
]

SOURCE_LABEL = "the string was drawn from"


def _load(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8") as handle:
        return {row["benchmark_id"]: row for row in csv.DictReader(handle)}


def _split(cell: str) -> list[str]:
    return [part.strip() for part in str(cell).split("||")]


def _short_source(raw: str) -> str:
    # supporting_sources are "Corpus/text_id/sentence_id"; the corpus name is enough here.
    return str(raw).split("/", 1)[0].strip()


def _top3(row: dict, star_index) -> list[dict]:
    readings = _split(row.get("suggestions", ""))
    sources = _split(row.get("supporting_sources", ""))
    out = []
    for i, reading in enumerate(readings[:3]):
        source = sources[i] if i < len(sources) else ""
        out.append(
            {
                "rank": i + 1,
                "reading": reading,
                "source": _short_source(source),
                "star": (star_index is not None and i == star_index),
            }
        )
    return out


def build_cases() -> list[dict]:
    loaded: dict[Path, dict] = {}
    for path in (V4_BEFORE, V4_AFTER, HOLD_BEFORE, HOLD_AFTER):
        loaded[path] = _load(path)

    cases = []
    for spec in CASES:
        before_row = loaded[spec["before_file"]][spec["id"]]
        after_row = loaded[spec["after_file"]][spec["id"]]
        cases.append(
            {
                "id": spec["id"],
                "tag": spec["tag"],
                "typed": before_row.get("query_input", ""),
                "edition": before_row.get("expected_transliteration", ""),
                "source": "{} / {}".format(
                    before_row.get("expected_source_text_id", ""),
                    before_row.get("expected_source_sentence_id", ""),
                ),
                "moved": spec["moved"],
                "question": spec["question"],
                "options": spec["options"],
                "before": _top3(before_row, spec["star_before"]),
                "after": _top3(after_row, spec["star_after"]),
            }
        )
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()

    cases = build_cases()
    page = TEMPLATE.replace("__CASES__", json.dumps(cases, ensure_ascii=False))
    page = page.replace("__CASE_COUNT__", str(len(cases)))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {output}")
    print("Open it in a browser, or publish it, and send the link to the reviewer.")


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Expert round 2 — five before/after ranking cases</title>
<style>
  :root {
    --ground:#F3F4F1; --raised:#FBFBF9; --ink:#161A18; --stone:#6D746E;
    --faience:#1A6B7A; --faience-soft:#E2EDEF; --rubric:#A63A2E; --edge:#DCDFD8;
    --moved:#8A5A00; --moved-soft:#F5ECD6;
    --shadow:0 1px 2px rgba(22,26,24,.04), 0 8px 24px rgba(22,26,24,.05);
    --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
    --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --ground:#141715; --raised:#1C201D; --ink:#E7EAE4; --stone:#9AA39B;
      --faience:#62B9C7; --faience-soft:#1B3439; --rubric:#D97A68; --edge:#2C312D;
      --moved:#E0B761; --moved-soft:#33291200;
      --shadow:0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.28);
    }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--ground); color:var(--ink);
         font-family:var(--serif); font-size:17px; line-height:1.6;
         -webkit-font-smoothing:antialiased; }
  .wrap { max-width:1000px; margin:0 auto; padding:0 1.5rem 6rem; }
  header { padding:3.5rem 0 1.5rem; max-width:70ch; }
  .eyebrow { font-family:var(--mono); font-size:.72rem; letter-spacing:.14em;
             text-transform:uppercase; color:var(--faience); margin-bottom:1rem; }
  h1 { font-size:clamp(1.8rem,4vw,2.6rem); line-height:1.12; margin:0 0 1rem;
       font-weight:600; letter-spacing:-.015em; }
  p { margin:0 0 1rem; max-width:70ch; }
  .quiet { color:var(--stone); }
  a { color:var(--faience); }
  h2 { font-size:1rem; letter-spacing:.1em; text-transform:uppercase;
       font-family:var(--mono); font-weight:500; color:var(--stone);
       margin:3.5rem 0 1.4rem; padding-bottom:.5rem; border-bottom:1px solid var(--edge); }
  .rail { position:sticky; top:0; z-index:10; display:flex; align-items:center; gap:1rem;
          background:color-mix(in srgb, var(--ground) 92%, transparent);
          backdrop-filter:blur(8px); border-bottom:1px solid var(--edge);
          padding:.6rem 1.5rem; }
  .rail-inner { max-width:1000px; margin:0 auto; width:100%; display:flex;
                align-items:center; gap:1rem; flex-wrap:wrap; }
  .rail-label { font-family:var(--mono); font-size:.7rem; letter-spacing:.06em;
                text-transform:uppercase; color:var(--stone); white-space:nowrap; }
  .track { flex:1; min-width:120px; height:3px; background:var(--edge);
           border-radius:99px; overflow:hidden; }
  .fill { height:100%; width:0%; background:var(--faience); transition:width .3s ease; }
  .case { background:var(--raised); border:1px solid var(--edge); border-radius:4px;
          box-shadow:var(--shadow); margin-bottom:1.8rem; overflow:hidden; }
  .case-head { padding:1.3rem 1.6rem 0; }
  .case-num { font-family:var(--mono); font-size:.75rem; letter-spacing:.08em;
              color:var(--rubric); margin-bottom:.5rem; }
  .case-num .tag { color:var(--stone); text-transform:none; letter-spacing:0; }
  .field { display:grid; grid-template-columns:8.5rem 1fr; gap:.3rem 1rem;
           margin:.2rem 0 1rem; }
  @media (max-width:620px){ .field { grid-template-columns:1fr; gap:.1rem; } }
  .field dt { font-family:var(--mono); font-size:.64rem; letter-spacing:.06em;
              text-transform:uppercase; color:var(--stone); padding-top:.2rem; }
  .field dd { margin:0; }
  .typed { font-family:var(--mono); font-size:.95rem; }
  .edition { font-size:1.02rem; }
  .srcid { font-family:var(--mono); font-size:.78rem; color:var(--stone); }
  .cols { display:grid; grid-template-columns:1fr 1fr; gap:1px; background:var(--edge);
          border-top:1px solid var(--edge); border-bottom:1px solid var(--edge); }
  @media (max-width:620px){ .cols { grid-template-columns:1fr; } }
  .col { background:var(--raised); padding:1.2rem 1.6rem; }
  .col h3 { font-family:var(--mono); font-size:.66rem; letter-spacing:.08em;
            text-transform:uppercase; color:var(--stone); margin:0 0 .8rem; font-weight:500; }
  .col.after h3 { color:var(--faience); }
  .sug { display:grid; grid-template-columns:1.4rem 1fr; gap:.5rem; padding:.4rem 0;
         border-top:1px dotted var(--edge); align-items:baseline; }
  .sug:first-of-type { border-top:0; }
  .sug .rk { font-family:var(--mono); font-size:.78rem; color:var(--stone);
             font-variant-numeric:tabular-nums; }
  .sug .rd { font-size:1.02rem; line-height:1.4; word-break:break-word; }
  .sug .src { font-family:var(--mono); font-size:.72rem; color:var(--stone); }
  .sug.star { background:var(--moved-soft); margin:0 -.6rem; padding:.4rem .6rem;
              border-radius:3px; border-top:0; }
  .sug.star .rd { color:var(--moved); font-weight:600; }
  .sug.star .rk { color:var(--moved); }
  .star-tag { display:inline-block; font-family:var(--mono); font-size:.6rem;
              letter-spacing:.08em; text-transform:uppercase; color:var(--moved);
              border:1px solid var(--moved); border-radius:99px; padding:.05rem .4rem;
              margin-left:.4rem; vertical-align:middle; }
  .moved { padding:1rem 1.6rem 0; }
  .moved p { font-size:.95rem; color:var(--ink); margin:0;
             border-left:2px solid var(--moved); padding-left:.9rem; }
  .verdict { padding:1.1rem 1.6rem 1.5rem; }
  .q { font-size:1.02rem; margin:0 0 .9rem; }
  .choices { display:flex; flex-wrap:wrap; gap:.5rem; }
  .choice { position:relative; }
  .choice input { position:absolute; opacity:0; width:0; height:0; }
  .choice span { display:inline-block; padding:.4rem .85rem; border:1px solid var(--edge);
                 border-radius:99px; font-size:.9rem; cursor:pointer; background:var(--raised); }
  .choice input:checked + span { background:var(--faience); border-color:var(--faience);
                                 color:var(--raised); }
  .choice input:focus-visible + span { outline:2px solid var(--faience); outline-offset:2px; }
  textarea { width:100%; min-height:56px; resize:vertical; margin-top:.7rem;
             padding:.55rem .7rem; border:1px solid var(--edge); border-radius:3px;
             background:var(--ground); color:var(--ink); font-family:var(--serif);
             font-size:.92rem; line-height:1.5; }
  textarea:focus-visible { outline:2px solid var(--faience); outline-offset:1px; }
  .actions { position:sticky; bottom:0; display:flex; gap:.7rem; align-items:center;
             flex-wrap:wrap; padding:.9rem 1.5rem; margin-top:2.5rem;
             background:color-mix(in srgb, var(--ground) 94%, transparent);
             backdrop-filter:blur(8px); border-top:1px solid var(--edge); }
  button { font-family:var(--mono); font-size:.78rem; letter-spacing:.04em;
           padding:.55rem 1.1rem; border-radius:3px; border:1px solid var(--faience);
           background:var(--faience); color:var(--raised); cursor:pointer; }
  button.ghost { background:transparent; color:var(--faience); }
  button:focus-visible { outline:2px solid var(--faience); outline-offset:2px; }
  .saved { font-family:var(--mono); font-size:.74rem; color:var(--stone); }
  footer { margin-top:2.5rem; padding-top:1.4rem; border-top:1px solid var(--edge); }
  @media (prefers-reduced-motion: reduce){ * { transition:none !important; } }
</style>
</head>
<body>
<div class="rail"><div class="rail-inner">
  <span class="rail-label">Answered <span id="done">0</span>/__CASE_COUNT__</span>
  <span class="track"><span class="fill" id="fill"></span></span>
  <span class="rail-label">saved in this browser only</span>
</div></div>

<div class="wrap">
  <header>
    <div class="eyebrow">Request for expert judgement</div>
    <h1>One ranking decision, five before/after cases</h1>
    <p>
      The tool searches a corpus of about 130,000 real Ancient Egyptian sentences for the
      rows that most resemble a string you give it, and shows its three best matches in
      order, with the corpus evidence behind each. It never invents a reading. This page
      tests one change to the rule that decides that order. On each of these five strings
      the change moves a specific suggestion up or down — once for the better, four times
      arguably for the worse. The automatic score cannot tell an improvement from a loss
      here; your reading can.
    </p>
    <p class="quiet">
      For each case, look at the two orderings and say which you would rather have been
      shown. There is no answer being checked against you. Your answers stay in this
      browser until you export them — nothing is uploaded. Under 15 minutes.
    </p>
  </header>

  <h2>The five cases</h2>
  <div id="cases"></div>

  <footer>
    <p class="quiet">
      Suggestions are drawn from the openly licensed part of the Thesaurus Linguae
      Aegyptiae plus the AES, BBAW and Ramses sentence corpora. Bracket marks
      (⸢…⸣, […], (…), ⸮…?) are the corpus editors' own — damaged, restored or uncertain
      signs — not added by the tool. Transliteration follows TLA / Berlin conventions.
    </p>
  </footer>
</div>

<div class="actions">
  <button id="export">Download my answers (CSV)</button>
  <button class="ghost" id="clear">Clear my answers</button>
  <span class="saved" id="savedNote"></span>
</div>

<script>
  const CASES = __CASES__;
  const KEY = "egy-round2-answers-v1";
  const state = JSON.parse(localStorage.getItem(KEY) || "{}");
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
    {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

  function sugRows(list) {
    return list.map((s) => `
      <div class="sug ${s.star ? "star" : ""}">
        <span class="rk">${s.rank}.</span>
        <span><span class="rd">${esc(s.reading)}</span>
          ${s.source ? `<span class="src"> — ${esc(s.source)}</span>` : ""}
          ${s.star ? `<span class="star-tag">moved</span>` : ""}</span>
      </div>`).join("");
  }

  function render() {
    document.getElementById("cases").innerHTML = CASES.map((c) => {
      const choices = c.options.map((o) => `
        <label class="choice">
          <input type="radio" name="v-${c.id}" value="${esc(o.value)}"
            ${state[c.id]?.verdict === o.value ? "checked" : ""}>
          <span>${esc(o.label)}</span>
        </label>`).join("");
      return `
      <article class="case" id="${c.id}">
        <div class="case-head">
          <div class="case-num">${c.id} &nbsp;·&nbsp; <span class="tag">${esc(c.tag)}</span></div>
          <dl class="field">
            <dt>Typed</dt><dd class="typed">${esc(c.typed)}</dd>
            <dt>Edition sentence</dt><dd class="edition">${esc(c.edition)}</dd>
            <dt>Source</dt><dd class="srcid">${esc(c.source)}</dd>
          </dl>
        </div>
        <div class="cols">
          <div class="col before"><h3>Before — current order</h3>${sugRows(c.before)}</div>
          <div class="col after"><h3>After — proposed order</h3>${sugRows(c.after)}</div>
        </div>
        <div class="moved"><p>${esc(c.moved)}</p></div>
        <div class="verdict">
          <p class="q">${esc(c.question)}</p>
          <div class="choices">${choices}</div>
          <textarea placeholder="Optional: one line on what decides it for you."
            data-note="${c.id}">${esc(state[c.id]?.note || "")}</textarea>
        </div>
      </article>`;
    }).join("");
    wire();
    progress();
  }

  function wire() {
    document.querySelectorAll('input[type="radio"]').forEach((input) => {
      input.addEventListener("change", (e) => {
        const id = e.target.name.slice(2);
        state[id] = Object.assign({}, state[id], {verdict: e.target.value});
        save();
      });
    });
    document.querySelectorAll("textarea[data-note]").forEach((area) => {
      area.addEventListener("input", (e) => {
        const id = e.target.dataset.note;
        state[id] = Object.assign({}, state[id], {note: e.target.value});
        save();
      });
    });
  }

  function save() {
    localStorage.setItem(KEY, JSON.stringify(state));
    document.getElementById("savedNote").textContent =
      "saved " + new Date().toLocaleTimeString();
    progress();
  }

  function progress() {
    const done = CASES.filter((c) => state[c.id]?.verdict).length;
    document.getElementById("done").textContent = done;
    document.getElementById("fill").style.width =
      (done / CASES.length * 100).toFixed(1) + "%";
  }

  document.getElementById("export").addEventListener("click", () => {
    const head = ["case", "typed", "edition_sentence", "source",
                  "before_top1", "after_top1", "answer", "answer_label", "reasoning"];
    const cell = (v) => '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"';
    const rows = CASES.map((c) => {
      const val = state[c.id]?.verdict || "";
      const opt = c.options.find((o) => o.value === val);
      return [
        c.id, c.typed, c.edition, c.source,
        c.before[0]?.reading || "", c.after[0]?.reading || "",
        val, opt ? opt.label : "", state[c.id]?.note || "",
      ].map(cell).join(",");
    });
    const blob = new Blob(["\\ufeff" + [head.join(","), ...rows].join("\\n")],
                          {type: "text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "expert_round_2_answers.csv"; a.click();
    URL.revokeObjectURL(url);
  });

  document.getElementById("clear").addEventListener("click", () => {
    if (!confirm("Clear every answer on this page?")) return;
    Object.keys(state).forEach((k) => delete state[k]);
    localStorage.removeItem(KEY);
    render();
    document.getElementById("savedNote").textContent = "cleared";
  });

  render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
