# Orientation check and live Phase 4 run, 15 October 2026

Model `qwen3-vl:4b-instruct` (digest `ee4b975b58c1`), prompt `reader-v2#eddb030d`. Same machine and settings as the model comparison (i7-1260P, 32 GB, T550 4 GB GPU; about 1.8 of the model's 4.5 GB on the GPU; temperature 0, thinking off, output cap 2,048 tokens, context 8,192, images at most 1,600 px). Raw report and resume file: `eval_runs/report_orientation_4b.json` (not committed).

## 1. Orientation judgement (`evaluate --orientation`)

Each of the 10 synthetic pages was sent as stored (upright) and turned 90°, 180° and 270° clockwise in memory (40 calls). A turn is acted on when the judgement is not "upright" with confidence ≥ 0.8.

| Page sent | Calls | Judged upright | Detected as turned | Wrongly turned | No valid reply | Seconds per call |
|---|---|---|---|---|---|---|
| Upright | 10 | 10 (correct) | n/a | 0 | 0 | 76 |
| Turned 90° | 10 | 10 | 0 | 0 | 0 | 104 |
| Turned 180° | 10 | 9 | 0 | 0 | 1 (timed out at 15 min) | 97 |
| Turned 270° | 10 | 10 | 0 | 0 | 0 | 103 |

- **The model never noticed a turned page.** Every valid judgement was "upright", with confidence 0.98–1.0. Layer c therefore never acted: 0 pages fixed and 30 missed (one of these was the timeout).
- **It never did harm either.** No page was turned the wrong way, and layer c added no time, because a second read happens only when a page is flagged.
- **Turned pages are slower:** about 100 s per call against 76 s upright.
- **One upside-down page made the model ramble** (economics student 2, turned 180°): the first reply ran into the 2,048-token cap, and the retry ran into the 15-minute call timeout. Generation on this laptop is about 2.3 tokens per second, so a reply that runs to the cap takes about the whole timeout.
- **One transient model-server error:** Ollama returned HTTP 500 after about 3 minutes on mathematics student 1 turned 180°, with no reason in its log. The same call succeeded when it was run again.

## 2. Live end-to-end run on the owner's test upload

The owner's chemistry upload: 4 students, covers with the phone-scan look, student 2's answer page upside down (as `merge_with_covers.py --rotate 2 --photo`). Uploaded, split, transcribed and marked by the real worker.

- **Splitting and stack rotation (layer b):** all 8 pages went to the right students. This run found a bug: covers tilted about a degree gave `rotation_stack` = 359, because zxing reports the exact angle. The angle is now snapped to quarter turns (commit `e3d2a9b`, tested).
- **Automatic check (layer c):** student 2's upside-down page was judged "upright" with confidence 1.0, so it was not turned. It was still read with CER 8.7 % (other pages: 0.7–1.6 %) and marked 10 out of 15 against an expected 14.
- **Teacher rotation (layer a):** not exercised with the real model here. It is covered by the backend tests and the browser test (rotate, undo, reload).
- **Time:** 22 minutes of AI time for 4 one-page scripts (reading 67–120 s per page, the rest marking). All 4 scripts reached `ai_marked`.

## Conclusions

1. With this model, **layer c does not work**: it misses every turned page. It is harmless and free (never wrong, no extra calls), so it can stay on for future models. Teachers must rely on **layer b** (stack rotation from the cover's QR, which is reliable) and **layer a** (the rotate control).
2. **Upside-down answer pages behind an upright cover** (the owner's test case) are not corrected automatically today. The teacher sees the page upside down in the review screen, turns it with one key (`r` twice), and can ask for a fresh read.
3. **Pipeline risk found:** a page that makes the model ramble costs up to 15 minutes per attempt, and a timeout is treated as "model server unavailable", so the job is retried again later. On a night run, one such page could waste an hour or more. A suggested fix is in the Phase 4 report for the owner to decide.

## Caveats

Synthetic typed pages; one model; one run per configuration. Real handwriting may behave differently.
