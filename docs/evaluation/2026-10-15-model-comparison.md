# Model comparison, 15 October 2026

Data: the owner's synthetic set (`margin_test_scripts/synthetic_scripts`): 10 scripts (chemistry 4, economics 3, mathematics 3), one page each, 57 questions with teacher-expected marks, 8 of them `language_expression` cases (correct idea, weak English). Pages are typed handwriting-style fonts on photographed-looking paper; **they are much easier than real handwriting**, so reading figures are an upper bound. Raw reports and the resume cache are in `eval_runs/` (not committed).

Machine: Intel Core i7-1260P, 32 GB RAM, NVIDIA T550 Laptop GPU (4 GB). Ollama 0.40.3. Models run partly on the CPU (the 4B about half and half). Settings: temperature 0, thinking off, output cap 2048 tokens, context 8192 tokens, page images at most 1600 px. Each run ran alone (no competing work). Prompts `reader-v1#f4062095`, `marker-v1`, `marker-lines-v1`.

## Reading

| Model | Pages | CER | WER | Key-token recall | Invalid | Seconds per page |
|---|---|---|---|---|---|---|
| qwen3-vl:2b-instruct | 10 | 1.3 % | 1.0 % | 98.1 % | 0 % | 44 |
| qwen3-vl:4b-instruct | 10 | 0.8 % | 0.8 % | 98.5 % | 0 % | 100 |

Both read the synthetic pages almost perfectly; the 4B is slightly more accurate and 2.3 times slower.

## Marking (57 questions)

"reader" = marking the model's own transcription (the real pipeline); "truth" = marking the true transcription (the marker alone). Exact = proposed question mark equals the expected mark (failed questions count as disagreements). MAD = mean absolute difference over answered questions. Lang = the 8 `language_expression` questions; "lost" = marks proposed below the expected mark on those.

| Marker | Evidence | Input | Exact | MAD | Failed | Lang exact | Lang lost | Lang called conceptual | Seconds per script |
|---|---|---|---|---|---|---|---|---|---|
| qwen3-vl:4b-instruct | quote | reader | **82 %** | 0.20 | 1 | 88 % | 2 | 0 | 299 |
| qwen3-vl:4b-instruct | quote | truth | 81 % | 0.23 | 1 | 88 % | 2 | 0 | 256 |
| qwen3-vl:4b-instruct | lines | reader | 72 % | 0.25 | 6 | 88 % | 2 | 0 | 210 |
| qwen3-vl:4b-instruct | lines | truth | 72 % | 0.22 | 6 | **100 %** | **0** | 0 | 211 |
| qwen2.5:7b (text) | quote | truth | 67 % | 0.35 | 5 | 75 % | 4 | 0 | 282 |
| qwen2.5:7b (text) | lines | truth | 75 % | 0.27 | 2 | 75 % | 2 | 0 | 227 |
| qwen3-vl:2b-instruct | quote | both | not reported | | | | | | |

- **qwen3-vl:2b-instruct as a marker:** its full results were lost when the first, non-resumable run was stopped, and on the owner's instruction it was not re-run. Its log shows 48 questions failing validation because the evidence was paraphrased rather than quoted, plus one point mismatch and one reply cut off at the cap. Not a candidate marker.
- **Per subject, truth input, exact agreement:** 4B quote: chemistry 21/24, economics 11/15, mathematics 14/18. 4B lines: 16/24, 10/15, 15/18. qwen2.5 quote: 17/24, 10/15, 11/18. qwen2.5 lines: 18/24, 11/15, 14/18.
- **Totals on the true transcription (expected 100 marks):** 4B quote proposed 91 (3 over, 10 under); 4B lines 102 (7 over, 4 under); qwen2.5 quote 77 (3 over, 15 under); qwen2.5 lines 90 (6 over, 9 under). The models lean towards under-marking, except the 4B with line evidence, which leans slightly generous.
- **Weak English:** no model labelled a weak-English answer a conceptual error. The 4B (quote) lost 2 marks on one economics question (expected 2, proposed 0); with line evidence it lost none.
- **Why questions failed:** 4B with line evidence: mostly `marker_points_mismatch` (a point left out or repeated); 4B with quotes: one invented quote and one point mismatch; qwen2.5: missing or invented evidence.

## Time split (4B, per 10 one-page scripts)

| Step | Time |
|---|---|
| Reading (10 pages) | 17 min |
| Marking, quote design | 43–50 min |
| Marking, line design | 35 min |

Marking takes about three quarters of the time: one call per question (6 per chemistry script), each 40–60 s. Projection for a class of 50 scripts with 4 pages each on this laptop, 4B for both: about 5½ h reading (200 pages × 100 s) plus 3½–4 h marking (more for long answers), so **9 to 10 hours**, at the edge of one night.

## Recommendation for this hardware

1. **Default: `qwen3-vl:4b-instruct` for both reading and marking, quote evidence.** Best agreement (81–82 %), fewest failed questions (1 of 57), one model in memory (no switching), and reading slightly better than the 2B. Recorded as D-048.
2. **Next, a cheap fix before switching evidence design:** give each question its own output schema listing exactly its point ids (required, each once). Most of the line design's failures were points left out or repeated, which the schema would prevent; with that fix the line design (perfect on the weak-English cases, evidence guaranteed verbatim, about 25 % faster marking) may overtake quotes. Re-evaluate both designs after the fix.
3. **Not recommended:** qwen3-vl:2b-instruct as a marker (paraphrases evidence); qwen2.5:7b as a marker (lower agreement, under-awards, and a second 4.7 GB model would have to share the 4 GB GPU).
4. **Possible fast mode, not yet recommended:** 2B for reading (44 s per page) with the 4B for marking would cut a 50-script night to roughly 6–7 hours. The 2B read the synthetic pages almost as well, but real handwriting may separate them; decide after real scripts are available.
5. **qwen3-vl:8b-instruct** was not evaluated (the thinking variant was removed). It would not fit the GPU and would likely be too slow for one night on this machine; worth testing on a school server with a larger GPU.

## Whole-script marking in one call

Worth testing, after the per-question schema fix. Today each question repeats the whole answer in its prompt; one call per script would read the answer once and should save prompt-processing time (likely 25–40 % of marking time). Risks: a long structured reply is harder for small models; one bad question must not invalidate the others (validate per question inside the reply, re-ask only the failed questions); long real scripts must still fit the context. Test with the evaluation command as a third design, compared on agreement, failures and time.

## Caveats

- Synthetic typed pages; small sample (57 questions, 8 language cases: one question changes the language figure by 12.5 points). Real, consented scripts with teacher-typed transcriptions are needed before trusting these numbers.
- One run per configuration at temperature 0; repeat runs were not made.
