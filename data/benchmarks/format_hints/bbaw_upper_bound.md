# BBAW upper bound on quadrat hints (item B, 2026-09-06)

Eligible rows: 11,386. Split seed 7: dev 5,693 / test 5,693. Hint precision 1.0000 (64,021/64,021).
Training frame 120,226 of 130,472 rows after the memorisation guard.

`as_pasted` is the importer's own grouping handed back unchanged — the
trivial ceiling, printed for orientation only.

```
config                 shape              half       n       P      R     F1  exact
-----------------------------------------------------------------------------------
controls_deleted       unspaced           dev     5693   0.750  0.815  0.781  0.547
as_pasted              as_pasted          dev     5693   1.000  1.000  1.000  1.000
controls_deleted       unspaced           test    5693   0.753  0.819  0.784  0.541
as_pasted              as_pasted          test    5693   1.000  1.000  1.000  1.000
hints_0.25             unspaced+controls  dev     5693   0.948  0.934  0.941  0.639
hints_0.25             unspaced+controls  test    5693   0.946  0.930  0.938  0.625
hints_0.5              unspaced+controls  dev     5693   0.949  0.934  0.941  0.642
hints_0.5              unspaced+controls  test    5693   0.947  0.930  0.938  0.628
hints_1.0              unspaced+controls  dev     5693   0.952  0.934  0.943  0.645
hints_1.0              unspaced+controls  test    5693   0.949  0.930  0.940  0.631
hints_2.0              unspaced+controls  dev     5693   0.963  0.935  0.949  0.654
hints_2.0              unspaced+controls  test    5693   0.960  0.931  0.945  0.643
```

Best unspaced F1 on dev: quadrat_crossed=2.0 (F1 0.9485).

<!-- Appended by hand: the hard constraint the script cannot measure itself. -->
The pre-registered selection is "best dev F1 **subject to** expert paste 8/8 in
`--stage auto`". `scripts/run_expert_paste_eval.py --stage auto --quadrat-crossed C`,
run at each candidate:

```
C=2.0   passed 7/8   [FAIL] PASTE_005  Layout-aware editor export
C=1.0   passed 8/8
C=0.5   passed 8/8
C=0.25  passed 8/8
```

So 2.0 is rejected and **quadrat_crossed = 1.0 is the selected constant** (test half:
F1 0.940, exact 0.631, against 0.784 / 0.541 with the controls deleted). See
`docs/format-hints-2026-09-06.md`.
