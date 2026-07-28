"""Render the expert review sheet as a self-contained page a reviewer can work in.

A CSV is fine for a machine and poor for a specialist: the hieroglyphs do not render,
the alternatives are a packed string, and there is nowhere to think. This produces a
single HTML file with the cases laid out for reading, verdict controls that save to the
browser's own storage, and an export button that hands back a CSV in the same shape as
the input sheet.

Nothing is sent anywhere. The reviewer's notes stay in their browser until they choose
to download them.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SHEET_PATH = "data/benchmarks/expert_review_sheet.csv"
MODEL_EVAL_PATH = "data/benchmarks/reading_model_eval_clean.csv"
OUTPUT_PATH = "data/benchmarks/expert_review.html"


def parse_alternatives(raw: str) -> list[dict]:
    out: list[dict] = []
    for part in str(raw).split("|"):
        name, _, share = part.strip().rpartition(":")
        if not name:
            continue
        try:
            value = float(share)
        except ValueError:
            continue
        out.append({"reading": name.strip(), "share": value})
    return out


def build_cases(sheet: pd.DataFrame) -> list[dict]:
    cases: list[dict] = []
    for _, row in sheet.iterrows():
        cases.append(
            {
                "id": str(row["case"]),
                "type": str(row["disagreement_type"]),
                "sign": str(row["sign"]),
                "sentence": str(row["sentence_context"]),
                "model": str(row["model_reading"]),
                "tla": str(row["tla_editorial_reading"]),
                "attested": int(row["times_sign_attested"]),
                "alternatives": parse_alternatives(row["attested_alternatives"]),
            }
        )
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", default=SHEET_PATH)
    parser.add_argument("--eval", default=MODEL_EVAL_PATH)
    parser.add_argument("--output", default=OUTPUT_PATH)
    args = parser.parse_args()

    sheet = pd.read_csv(args.sheet).fillna("")
    cases = build_cases(sheet)

    headline = {}
    eval_path = Path(args.eval)
    if eval_path.exists():
        evaluation = pd.read_csv(eval_path)
        last = evaluation.iloc[-1]
        headline = {
            "sentences": int(last["corpus_sentences"]),
            "ambiguous_types": int(last["ambiguous_sign_types"]),
            "baseline": float(last["acc_ambiguous_most_frequent"]),
            "model": float(last["acc_ambiguous_context"]),
            "coverage": float(last["coverage_with_fallback"]),
        }

    page = TEMPLATE.replace("__CASES__", json.dumps(cases, ensure_ascii=False))
    page = page.replace("__HEADLINE__", json.dumps(headline))
    page = page.replace("__CASE_COUNT__", str(len(cases)))
    for key, fallback in [
        ("sentences", 0),
        ("ambiguous_types", 0),
    ]:
        page = page.replace(f"__{key.upper()}__", f"{headline.get(key, fallback):,}")
    page = page.replace("__BASELINE__", f"{headline.get('baseline', 0) * 100:.1f}")
    page = page.replace("__MODEL__", f"{headline.get('model', 0) * 100:.1f}")
    page = page.replace("__COVERAGE__", f"{headline.get('coverage', 0) * 100:.1f}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    print(f"Wrote review page with {len(cases)} cases to {output}")
    print(f"Open it in a browser, or publish it, and send the link to the reviewer.")


TEMPLATE = """<title>Reading disagreements for review — Egyptian sign multivalence</title>
<style>
  :root {
    --ground: #F3F4F1;
    --raised: #FBFBF9;
    --ink: #161A18;
    --stone: #6D746E;
    --faience: #1A6B7A;
    --faience-soft: #E2EDEF;
    --rubric: #A63A2E;
    --edge: #DCDFD8;
    --shadow: 0 1px 2px rgba(22, 26, 24, .04), 0 8px 24px rgba(22, 26, 24, .05);
    --serif: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua",
             "URW Palladio L", Georgia, serif;
    --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;
    --glyph: "Noto Sans Egyptian Hieroglyphs", "Segoe UI Historic", "Aegyptus",
             "JSesh", sans-serif;
    --measure: 68ch;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --ground: #141715;
      --raised: #1C201D;
      --ink: #E7EAE4;
      --stone: #9AA39B;
      --faience: #62B9C7;
      --faience-soft: #1B3439;
      --rubric: #D97A68;
      --edge: #2C312D;
      --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.28);
    }
  }
  :root[data-theme="dark"] {
    --ground: #141715; --raised: #1C201D; --ink: #E7EAE4; --stone: #9AA39B;
    --faience: #62B9C7; --faience-soft: #1B3439; --rubric: #D97A68; --edge: #2C312D;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.28);
  }
  :root[data-theme="light"] {
    --ground: #F3F4F1; --raised: #FBFBF9; --ink: #161A18; --stone: #6D746E;
    --faience: #1A6B7A; --faience-soft: #E2EDEF; --rubric: #A63A2E; --edge: #DCDFD8;
    --shadow: 0 1px 2px rgba(22,26,24,.04), 0 8px 24px rgba(22,26,24,.05);
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--ground);
    color: var(--ink);
    font-family: var(--serif);
    font-size: 17px;
    line-height: 1.65;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 0 1.5rem 6rem; }

  /* progress rail */
  .rail {
    position: sticky; top: 0; z-index: 10;
    background: color-mix(in srgb, var(--ground) 92%, transparent);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--edge);
    display: flex; align-items: center; gap: 1rem;
    padding: .7rem 1.5rem;
  }
  .rail-inner {
    max-width: 1080px; margin: 0 auto; width: 100%;
    display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
  }
  .rail-label {
    font-family: var(--mono); font-size: .7rem; letter-spacing: .08em;
    text-transform: uppercase; color: var(--stone); white-space: nowrap;
  }
  .track { flex: 1; min-width: 120px; height: 3px; background: var(--edge); border-radius: 99px; overflow: hidden; }
  .fill { height: 100%; width: 0%; background: var(--faience); transition: width .3s ease; }

  header { padding: 4.5rem 0 2.5rem; max-width: var(--measure); }
  .eyebrow {
    font-family: var(--mono); font-size: .72rem; letter-spacing: .14em;
    text-transform: uppercase; color: var(--faience); margin-bottom: 1.1rem;
  }
  h1 {
    font-size: clamp(2rem, 4.4vw, 3rem); line-height: 1.1; margin: 0 0 1.2rem;
    font-weight: 600; letter-spacing: -.015em; text-wrap: balance;
  }
  .lede { font-size: 1.16rem; color: var(--ink); margin: 0 0 1.1rem; }
  p { margin: 0 0 1.1rem; max-width: var(--measure); }
  .quiet { color: var(--stone); }
  a { color: var(--faience); }

  .facts {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1px; background: var(--edge); border: 1px solid var(--edge);
    border-radius: 3px; overflow: hidden; margin: 2rem 0 0;
  }
  .fact { background: var(--raised); padding: 1rem 1.1rem; }
  .fact dt {
    font-family: var(--mono); font-size: .68rem; letter-spacing: .07em;
    text-transform: uppercase; color: var(--stone); margin-bottom: .35rem;
  }
  .fact dd {
    margin: 0; font-size: 1.5rem; font-variant-numeric: tabular-nums;
    letter-spacing: -.02em;
  }

  .note {
    border-left: 2px solid var(--rubric); padding: .2rem 0 .2rem 1.1rem;
    margin: 2rem 0; max-width: var(--measure);
  }
  h2 {
    font-size: 1.05rem; letter-spacing: .1em; text-transform: uppercase;
    font-family: var(--mono); font-weight: 500; color: var(--stone);
    margin: 4rem 0 1.6rem; padding-bottom: .6rem; border-bottom: 1px solid var(--edge);
  }

  /* cases */
  .case {
    background: var(--raised); border: 1px solid var(--edge); border-radius: 3px;
    box-shadow: var(--shadow); margin-bottom: 1.6rem; overflow: hidden;
  }
  .case-grid { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); }
  @media (max-width: 820px) { .case-grid { grid-template-columns: 1fr; } }

  .case-left { padding: 1.6rem 1.7rem; border-right: 1px solid var(--edge); }
  @media (max-width: 820px) { .case-left { border-right: 0; border-bottom: 1px solid var(--edge); } }
  .case-num {
    font-family: var(--mono); font-size: .75rem; letter-spacing: .1em;
    color: var(--rubric); margin-bottom: 1rem;
  }
  .glyph {
    font-family: var(--glyph); font-size: 3.4rem; line-height: 1.25;
    margin: 0 0 .5rem; word-break: break-word;
  }
  .attest {
    font-family: var(--mono); font-size: .74rem; color: var(--stone);
    font-variant-numeric: tabular-nums; margin-bottom: 1.3rem;
  }
  .ctx-label {
    font-family: var(--mono); font-size: .66rem; letter-spacing: .09em;
    text-transform: uppercase; color: var(--stone); margin-bottom: .4rem;
  }
  .sentence { font-size: .97rem; line-height: 1.7; margin: 0; }

  .case-right { padding: 1.6rem 1.7rem; display: flex; flex-direction: column; gap: 1.2rem; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: .8rem; }
  @media (max-width: 560px) { .pair { grid-template-columns: 1fr; } }
  .reading-card { border: 1px solid var(--edge); border-radius: 3px; padding: .85rem .95rem; }
  .reading-card.model { border-color: var(--faience); background: var(--faience-soft); }
  .reading-card dt {
    font-family: var(--mono); font-size: .64rem; letter-spacing: .08em;
    text-transform: uppercase; color: var(--stone); margin-bottom: .4rem;
  }
  .reading-card.model dt { color: var(--faience); }
  .reading-card dd { margin: 0; font-size: 1.22rem; line-height: 1.35; word-break: break-word; }

  .alts { border-top: 1px solid var(--edge); padding-top: .9rem; }
  .alt-row {
    display: grid; grid-template-columns: minmax(0, 1fr) 44px 70px;
    align-items: center; gap: .6rem; padding: .18rem 0;
    font-size: .9rem;
  }
  .alt-name { word-break: break-word; }
  .alt-pct {
    font-family: var(--mono); font-size: .76rem; color: var(--stone);
    text-align: right; font-variant-numeric: tabular-nums;
  }
  .bar { height: 3px; background: var(--edge); border-radius: 99px; overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--stone); }

  .verdict { border-top: 1px solid var(--edge); padding-top: 1.1rem; }
  fieldset { border: 0; padding: 0; margin: 0 0 .8rem; }
  legend {
    font-family: var(--mono); font-size: .66rem; letter-spacing: .09em;
    text-transform: uppercase; color: var(--stone); padding: 0; margin-bottom: .55rem;
  }
  .choices { display: flex; flex-wrap: wrap; gap: .4rem; }
  .choice { position: relative; }
  .choice input { position: absolute; opacity: 0; width: 0; height: 0; }
  .choice span {
    display: inline-block; padding: .34rem .7rem; border: 1px solid var(--edge);
    border-radius: 99px; font-size: .84rem; cursor: pointer; background: var(--raised);
    transition: background .15s ease, border-color .15s ease, color .15s ease;
  }
  .choice input:checked + span {
    background: var(--faience); border-color: var(--faience); color: var(--raised);
  }
  .choice input:focus-visible + span { outline: 2px solid var(--faience); outline-offset: 2px; }
  textarea {
    width: 100%; min-height: 68px; resize: vertical; padding: .6rem .7rem;
    border: 1px solid var(--edge); border-radius: 3px; background: var(--ground);
    color: var(--ink); font-family: var(--serif); font-size: .92rem; line-height: 1.55;
  }
  textarea:focus-visible { outline: 2px solid var(--faience); outline-offset: 1px; }

  .actions {
    position: sticky; bottom: 0; background: color-mix(in srgb, var(--ground) 94%, transparent);
    backdrop-filter: blur(8px); border-top: 1px solid var(--edge);
    padding: .9rem 1.5rem; margin-top: 3rem;
    display: flex; gap: .7rem; align-items: center; flex-wrap: wrap;
  }
  button {
    font-family: var(--mono); font-size: .78rem; letter-spacing: .04em;
    padding: .55rem 1.1rem; border-radius: 3px; border: 1px solid var(--faience);
    background: var(--faience); color: var(--raised); cursor: pointer;
  }
  button.ghost { background: transparent; color: var(--faience); }
  button:focus-visible { outline: 2px solid var(--faience); outline-offset: 2px; }
  .saved { font-family: var(--mono); font-size: .74rem; color: var(--stone); }
  footer { margin-top: 3rem; padding-top: 1.6rem; border-top: 1px solid var(--edge); }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="rail">
  <div class="rail-inner">
    <span class="rail-label">Reviewed <span id="done">0</span>/__CASE_COUNT__</span>
    <span class="track"><span class="fill" id="fill"></span></span>
    <span class="rail-label" id="stored">saved in this browser</span>
  </div>
</div>

<div class="wrap">
  <header>
    <div class="eyebrow">Request for expert judgement</div>
    <h1>Where an automatic reader and the TLA edition disagree</h1>
    <p class="lede">
      A corpus-based tool proposes a reading for each hieroglyphic sign group from the
      readings that group is attested with, weighted by context. These __CASE_COUNT__ cases
      are the ones where its choice differs from the Thesaurus Linguae Aegyptiae edition
      in substance. The question is not who is right in the abstract — it is which reading
      you would defend here, and why.
    </p>
    <p class="quiet">
      Your verdicts stay in this browser until you export them. Nothing is uploaded.
    </p>

    <dl class="facts">
      <div class="fact"><dt>Corpus</dt><dd>__SENTENCES__</dd></div>
      <div class="fact"><dt>Multivalent signs</dt><dd>__AMBIGUOUS_TYPES__</dd></div>
      <div class="fact"><dt>Baseline accuracy</dt><dd>__BASELINE__%</dd></div>
      <div class="fact"><dt>With context</dt><dd>__MODEL__%</dd></div>
    </dl>

    <div class="note">
      <p style="margin:0">
        <strong>How these were chosen.</strong> Of 651 disagreements on held-out
        sentences, 259 were the same reading bracketed differently and 261 more involved
        a reading attested fewer than three times, which is usually a slip in the
        sign-to-reading alignment rather than a real alternative. Both groups were
        excluded. What remains are cases where two well-attested readings genuinely
        compete, capped at two per sign so the set covers 20 different signs.
      </p>
    </div>

    <p class="quiet">
      A note on the comparison: the TLA reading is itself an editorial decision, not
      ground truth. Several of these look like transcription conventions rather than
      reading choices — <em>nswt</em> against <em>nzw</em>, <em>sp</em> against
      <em>zp</em>. Saying so is a useful verdict.
    </p>
  </header>

  <h2>Cases</h2>
  <div id="cases"></div>

  <footer>
    <p class="quiet">
      Built from the Thesaurus Linguae Aegyptiae Earlier Egyptian corpus. Readings and
      counts come from that edition; the proposals come from a statistical model trained
      only on it. Sign groups and transliteration tokens are aligned one to one, and
      sentences where they are not are excluded.
    </p>
  </footer>
</div>

<div class="actions">
  <button id="export">Download my verdicts (CSV)</button>
  <button class="ghost" id="clear">Clear my answers</button>
  <span class="saved" id="savedNote"></span>
</div>

<script>
  const CASES = __CASES__;
  const KEY = "egy-review-verdicts-v1";
  const state = JSON.parse(localStorage.getItem(KEY) || "{}");

  const CHOICES = [
    ["model", "Model reading"],
    ["tla", "TLA reading"],
    ["both", "Both defensible"],
    ["neither", "Neither"],
  ];

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => (
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]
  ));

  function render() {
    document.getElementById("cases").innerHTML = CASES.map((c) => {
      const alts = c.alternatives.map((a) => `
        <div class="alt-row">
          <span class="alt-name">${esc(a.reading)}</span>
          <span class="bar"><span style="width:${Math.round(a.share * 100)}%"></span></span>
          <span class="alt-pct">${(a.share * 100).toFixed(0)}%</span>
        </div>`).join("");
      const choices = CHOICES.map(([value, label]) => `
        <label class="choice">
          <input type="radio" name="v-${c.id}" value="${value}"
            ${state[c.id]?.verdict === value ? "checked" : ""}>
          <span>${label}</span>
        </label>`).join("");
      return `
      <article class="case" id="${c.id}">
        <div class="case-grid">
          <div class="case-left">
            <div class="case-num">${c.id}</div>
            <p class="glyph">${esc(c.sign)}</p>
            <p class="attest">attested ${c.attested.toLocaleString()}× in the corpus</p>
            <div class="ctx-label">Sentence</div>
            <p class="sentence">${esc(c.sentence)}</p>
          </div>
          <div class="case-right">
            <div class="pair">
              <dl class="reading-card model">
                <dt>Model proposes</dt><dd>${esc(c.model)}</dd>
              </dl>
              <dl class="reading-card">
                <dt>TLA edition</dt><dd>${esc(c.tla)}</dd>
              </dl>
            </div>
            <div class="alts">
              <div class="ctx-label">All attested readings of this sign</div>
              ${alts}
            </div>
            <div class="verdict">
              <fieldset>
                <legend>Which reading would you defend here?</legend>
                <div class="choices">${choices}</div>
              </fieldset>
              <textarea placeholder="Why? Anything that decides it — grammar, parallels, period, or that the difference is only a transcription convention."
                data-note="${c.id}">${esc(state[c.id]?.note || "")}</textarea>
            </div>
          </div>
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
    const head = ["case", "sign", "sentence_context", "model_reading",
                  "tla_editorial_reading", "expert_agrees_with", "expert_reasoning"];
    const cell = (v) => '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"';
    const rows = CASES.map((c) => [
      c.id, c.sign, c.sentence, c.model, c.tla,
      state[c.id]?.verdict || "", state[c.id]?.note || "",
    ].map(cell).join(","));
    const blob = new Blob(["\\ufeff" + [head.join(","), ...rows].join("\\n")],
                          {type: "text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "expert_verdicts.csv"; a.click();
    URL.revokeObjectURL(url);
  });

  document.getElementById("clear").addEventListener("click", () => {
    if (!confirm("Clear every answer you have entered on this page?")) return;
    Object.keys(state).forEach((k) => delete state[k]);
    localStorage.removeItem(KEY);
    render();
    document.getElementById("savedNote").textContent = "cleared";
  });

  render();
</script>
"""


if __name__ == "__main__":
    main()
