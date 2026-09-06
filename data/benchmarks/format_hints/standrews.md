# Quadrat hints on real St Andrews input (item B, 2026-09-06)

1,701 lines with glyphs and a reading; public corpus 130,472 rows; memorisation guard passed (0 lines in the corpus).
Constant tested: quadrat_crossed = 1.0.

Fold: NFC, lowercase, delete `. ( ) [ ] {{ }} ⸢ ⸣`, nothing else.

```
shape        arm            q  lines       P      R     F1  exact  |grp-tok|
----------------------------------------------------------------------------
as_rendered  hints_off   0.00   1701   0.524  0.642  0.577  0.025      3.319
as_rendered  hints_on    1.00   1701   0.531  0.640  0.581  0.025      3.145
unspaced     hints_off   0.00   1701   0.559  0.617  0.587  0.027      2.357
unspaced     hints_on    1.00   1701   0.568  0.617  0.591  0.026      2.188

paired deltas (hints_on - hints_off), per shape:
  as_rendered  dF1 +0.0038  dexact +0.0000  d|grp-tok| -0.1740  improved 178  worsened 56  unchanged 1467
  unspaced     dF1 +0.0046  dexact -0.0005  d|grp-tok| -0.1699  improved 195  worsened 69  unchanged 1437

On Camilla's line (`urkIV-001`, line 2, St Andrews rendering) the hints make one real
correction on the as-rendered shape: the groups `𓈖𓏏 𓈖` become `𓈖 𓏏𓈖`, so the reading
`n.t n` becomes `n =tn` — the exact place the first expert trial flagged. The line's token
F1 does not move (the fold counts multisets and the line is wrong elsewhere: the `𓏤𓏤𓏤`
fillers read as `3`, `ꞽwꜥ.kw` split, the numeral `7` lost); on the unspaced shape the
hints change nothing on this line. The full per-shape printout is in the script's stdout
and is not committed: the St Andrews glyph groups and gold reading are CC BY-NC-SA and
stay out of this CC BY-SA data directory.
