# The reference number: what it is and how it was trained

Retina shows how many of 100 people may still be watching. That number comes from one small layer that is not a Meta model:
a ridge regression fitted offline on our own data. On 30-Oct-2026 the organizers ruled that a small self-trained layer like
this is acceptable as long as the README explains what the layer does, with its fitting details, the fixed weights are in the repo,
and Meta models clearly do the real work. This page is that documentation.

## What the layer does

It takes the average retention curve for videos of the same length and adjusts it up or down a little for this video. Nothing
else. It writes no text, makes no decision about the video and takes no part in the rewrite. At runtime it is a JSON file of
fixed numbers that plain Python multiplies and adds, in `ModeloPublico.predecir` ([`src/retina/publico.py`](../src/retina/publico.py)).
`RETINA_SOLO_MODELOS_META=1` turns it off.

## The data

- **Source:** Facebook retention curves of a large page in Mexico (Badabun), about 30,000 videos published from 2020 to 2026,
  with data up to 24-Oct-2026. Each video has a 41-point curve: how many people were still watching at each 2.5 % of its length.
- **Who owns it:** Badabun, the company behind this entry. The raw data stays private and is not in this repository.
- **What was left out:** videos with eligibility and videos about out-of-scope topics or out-of-scope topics
  ([`reglas/alcance-v1.json`](../reglas/alcance-v1.json), checked against the title and the first 40 spoken
  words). Revenue was never read.
- **What was removed:** creator names, from both the title and the words the model learns.

## The inputs

For each video, 1,703 numbers, all built by plain code ([`src/retina/predecir.py`](../src/retina/predecir.py)):

| Input | Size | How it is built |
|---|---|---|
| Length | 2 | Logarithm of the duration and its square |
| Posting time | 3 + 7 | Hour of day and day of the week |
| Format | 1 | Whether it is vertical (a reel) |
| Title words | 1,024 | Each word is hashed to one of 1,024 slots |
| Speech in the opening | 86 | When speech starts, how many words in 3 and 15 s, pauses, questions |
| First 25 spoken words | 512 | Each word is hashed to one of 512 slots |
| Average curve for its length | 41 | The starting point the layer adjusts |
| Opening sheet | 26 | What **Muse Spark Open** noted: hook, emotion, clarity, curiosity and five yes/no questions |
| Intercept | 1 | |

Speech comes from **Muse Voice Transcribe** when Retina runs. To build the training set we transcribed the archive offline with
Whisper (`transcribir_local.py`); that never runs in the app.

## The training

1. **Baseline.** For each video, the average curve of videos of the same length in one of five buckets (under 30 s, 30 to 60 s, 1
   to 2 min, 2 to 4 min, over 4 min), preferring the previous 90 days.
2. **Target.** The difference between the video's real curve and that baseline, at each of the 41 points.
3. **Fit.** Ridge regression in closed form: `W = (XᵀX + λI)⁻¹ XᵀY`, with no penalty on the intercept
   (`ajustar_ridge` in `predecir.py`). λ = 300, chosen by validation on 10 groups of held-out creators
   ([`eval/cualquier_video.py`](../eval/cualquier_video.py)). Training has no other randomness.
4. **Prediction.** `curve = baseline + x · W`, clipped between 0 and 1.

The file also holds the weights of an opening risk level. The public version does not use them: that traffic light did not pass
its rule ([`docs/decisiones.md`](decisiones.md)).

To rebuild the file, with access to the private data:

```bash
python -m retina.publico --base BASE.csv --voz VOZ.jsonl --fichas FICHAS.jsonl --salida modelos/retina-publico.json
```

## The fixed weights

[`modelos/retina-publico.json`](../modelos/retina-publico.json) is about 770 KB of plain JSON, so opening it runs no code. It holds
the 1,703 × 41 weight matrix, five average curves by length and the settings above. It has no videos, titles, creators, production
codes, per-video figures or revenue.

## How good it is

Modest, and we say so. Results are in the README and every rule is in [`docs/decisiones.md`](decisiones.md).

- Reading the opening improved the number on two held-out periods, by about 2 people per 1,000.
- Against the plain average for each length, for creators it had never seen, it lost one period and tied the other.
- **It cannot compare two versions of the same video.** It learned from differences between videos. On 41 rewritten openings
  the number fell in 27, rose in 7 and barely moved in 7, so Retina shows no number for the new opening.

Use it as a reference for what to expect, not as a promise.
