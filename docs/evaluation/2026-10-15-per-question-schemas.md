# Per-question output schemas, 15 October 2026

Re-run of the marking evaluation after the per-question schemas (D-054). Same data, machine and settings as `2026-10-15-model-comparison.md`: the owner's synthetic set, 10 one-page scripts, 57 questions, 8 of them `language_expression`. Model `qwen3-vl:4b-instruct` (`ee4b975b58c1`) reads and marks. Reading was reused from the cache (prompt `reader-v2#eddb030d`; CER 0.8 %). Marking prompts `marker-v2#6bf69283` (quotes) and `marker-lines-v2#268bfe02` (line numbers). Raw report: `eval_runs/report_schemas_4b.json` (not committed).

"reader" = marking the model's own transcription (the real pipeline); "truth" = marking the true transcription. Failed questions count as disagreements in the agreement rates. MAD is over answered questions.

## Overall (57 questions)

| Design | Input | Exact | Within 1 mark | MAD | Failed | Over-marked | Under-marked | Seconds per script |
|---|---|---|---|---|---|---|---|---|
| quotes | reader | 81 % | 89 % | 0.25 | 2 | 3 questions (+3) | 6 questions (−11) | 338 |
| quotes | truth | **86 %** | 95 % | **0.16** | 1 | 2 (+2) | 5 (−7) | 260 |
| lines | reader | 81 % | **95 %** | 0.25 | **0** | 4 (+4) | 7 (−10) | **212** |
| lines | truth | 79 % | 95 % | 0.30 | **0** | 4 (+4) | 8 (−13) | **202** |

### Compared with the evaluation before per-question schemas

| Design | Input | Exact before → now | MAD before → now | Failed before → now | Seconds per script before → now |
|---|---|---|---|---|---|
| quotes | reader | 82 % → 81 % | 0.20 → 0.25 | 1 → 2 | 299 → 338 |
| quotes | truth | 81 % → 86 % | 0.23 → 0.16 | 1 → 1 | 256 → 260 |
| lines | reader | 72 % → **81 %** | 0.25 → 0.25 | **6 → 0** | 210 → 212 |
| lines | truth | 72 % → **79 %** | 0.22 → 0.30 | **6 → 0** | 211 → 202 |

- **The schemas did what they were for.** The line design's failures were points left out or repeated (`marker_points_mismatch`); there are now none. Its exact agreement rose from 72 % to 79–81 %.
- **Quote design:** no point mismatches either. Its only failures are invented quotes (`marker_invented_evidence`, 3 questions over both inputs), which a schema cannot prevent.
- **On the real pipeline (model's own transcription), the two designs now agree as often** (81 % exact). The line design is closer more often (95 % within 1 mark against 89 %), never fails a question, and marks a script about **37 % faster** (212 s against 338 s).
- **Both designs still lean towards under-marking** (6–8 questions under, 3–4 over).

## Per subject

| Design | Input | Subject | Exact | Within 1 | MAD | Over (marks) | Under (marks) | Failed |
|---|---|---|---|---|---|---|---|---|
| quotes | reader | chemistry | 83 % | 92 % | 0.29 | 2 (+2) | 2 (−5) | 0 |
| quotes | reader | economics | 73 % | 87 % | 0.40 | 0 | 4 (−6) | 0 |
| quotes | reader | mathematics | 83 % | 89 % | 0.06 | 1 (+1) | 0 | 2 |
| quotes | truth | chemistry | 92 % | 96 % | 0.12 | 1 (+1) | 1 (−2) | 0 |
| quotes | truth | economics | 80 % | 93 % | 0.27 | 0 | 3 (−4) | 0 |
| quotes | truth | mathematics | 83 % | 94 % | 0.12 | 1 (+1) | 1 (−1) | 1 |
| lines | reader | chemistry | 88 % | 96 % | 0.17 | 2 (+2) | 1 (−2) | 0 |
| lines | reader | economics | 73 % | 93 % | 0.33 | 1 (+1) | 3 (−4) | 0 |
| lines | reader | mathematics | 78 % | 94 % | 0.28 | 1 (+1) | 3 (−4) | 0 |
| lines | truth | chemistry | 88 % | 96 % | 0.17 | 2 (+2) | 1 (−2) | 0 |
| lines | truth | economics | 67 % | 93 % | 0.53 | 1 (+1) | 4 (−7) | 0 |
| lines | truth | mathematics | 78 % | 94 % | 0.28 | 1 (+1) | 3 (−4) | 0 |

Economics is the hardest subject for both designs, and is mostly under-marked.

## Weak English (8 `language_expression` questions)

| Design | Input | Exact | Marks lost | Called a conceptual error |
|---|---|---|---|---|
| quotes | reader | 75 % | 5 | 0 |
| quotes | truth | 100 % | 0 | 0 |
| lines | reader | 88 % | 2 | 0 |
| lines | truth | 75 % | 5 | 0 |

- **No answer with weak English was labelled a conceptual error** in any configuration.
- **The ranking is not stable:** before the schemas, the line design was perfect on the true transcription and lost 2 marks on the model's own. Now the quote design is perfect on the true transcription. With 8 questions, one question moves the rate by 12.5 points, so neither design can be said to be better for weak English on this data.

## Recommendation

**Switch the default marker design to line numbers (`MARGIN_MARKER_EVIDENCE=lines`)**, with the per-question schemas, for this hardware and the demo:
- **Agreement:** the same exact agreement as quotes on the real pipeline (81 %), and more answers within 1 mark (95 % against 89 %).
- **Reliability:** no failed questions, so no script is sent to manual marking because of a malformed reply.
- **Speed:** about 37 % faster marking. A 50-script class with 6 questions each saves about an hour a night on this laptop.
- **Evidence:** always the student's own lines, copied by Margin, never paraphrased.

**Against it:**
- Quotes did better on the true transcription (86 % against 79 %). The real pipeline marks the model's transcription, where the two are level.
- Line evidence is coarser: a whole line is highlighted rather than an exact phrase.

The default changes only with the owner's approval (D-048).

## Caveats
Synthetic typed pages; one model; one run per configuration at temperature 0; 57 questions. Real, consented scripts with teacher-typed transcriptions are needed before trusting these differences, several of which are one or two questions.
