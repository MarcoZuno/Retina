# The reference number: what it is and how it was trained

Retina shows how many of every 100 people who get past the first 3 seconds may still be watching. That number comes from one
small layer that is not a Meta model:
a ridge regression fitted offline on our own data. On 30-Oct-2026 the organizers ruled that a small self-trained layer like
this is acceptable as long as the README explains what the layer does, with its fitting details, the fixed weights are in the repo,
and Meta models clearly do the real work. This page is that documentation.

## What the layer does

It takes the average retention curve for videos of the same length and adjusts it up or down a little for this video. Nothing
else. It writes no text, makes no decision about the video and takes no part in the rewrite. At runtime it is a JSON file of
fixed numbers that plain Python multiplies and adds, in `ModeloPublico.predecir` ([`src/retina/publico.py`](../src/retina/publico.py)).
`RETINA_SOLO_MODELOS_META=1` turns it off.

## The data

- **Source:** Facebook retention curves of a large page in Mexico (Badabun): 32,906 videos published from 2020 to 2026, with data
  up to 24-Oct-2026. Each video has a 41-point curve: how many people were still watching at each 2.5 % of its length.
- **What the curve does not see:** it stays near 100 until about 3 seconds at every length and drops right after, so Facebook seems
  to count only people who got that far (the shape is measured; the cause is our reading of it). In 2,953 videos of about a minute it
  reads 99.8 at 2.9 s and 79.8 at 4.4 s. People who leave earlier are not in this data, so Retina cannot see them.
- **Who owns it:** Badabun, the company behind this entry. The raw data stays private and is not in this repository.
- **What was left out:** videos with eligibility or no record of it, and videos about out-of-scope topics or out-of-scope topics
  ([`reglas/alcance-v1.json`](../reglas/alcance-v1.json), checked against the title and the first 40 spoken
  words). Revenue was never read.
- **What was used:** 23,710 videos. Of those, 974 have no speech and 9,003 have no opening sheet: they enter with zeros in those inputs.
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
Whisper (`transcribir_local.py`); that never runs in the app. The sheets used for training were written with no fixed temperature, 20
videos per call; the app asks for one video at temperature 0, so the two are not identical and we have not measured the difference.

## The training

1. **Baseline.** For each video, the average curve of videos of the same length in one of five buckets (under 30 s, 30 to 60 s, 1
   to 2 min, 2 to 4 min, over 4 min), preferring the previous 90 days.
2. **Target.** The difference between the video's real curve and that baseline, at each of the 41 points.
3. **Fit.** Ridge regression in closed form: `W = (XᵀX + λI)⁻¹ XᵀY`, with no penalty on the intercept
   (`ajustar_ridge` in `predecir.py`). λ = 300 was chosen from 10 to 3,000 on the latest 20 % of the training videos by date, in an
   earlier variant of the formula: one that kept paid videos and had no opening sheet
   ([`eval/cualquier_video.py`](../eval/cualquier_video.py), `ajustar`). It was not chosen again for the published file. Training has
   no other randomness.
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

- **The margin.** On creators hidden from training, at the moment the panel shows (15 s, or mid-video under 30 s), it missed by 8.9
  people out of 100 on average, against 10.4 for the fixed curve alone (23,710 videos, 5 groups). The harder check also hid the future:
  fitted before 2026 and measured on 1,992 later videos, it missed by 10.2, against 11.7. The panel uses the larger figure, rounded up:
  **give or take 11 people out of 100** ([`eval/margen_numero.py`](../eval/margen_numero.py)).
- **Most videos come out "similar".** In about 9 of 10 videos the number moves less than 9 people away from the fixed curve, which is
  less than the margin, so the panel says "similar to videos like yours" instead of inventing a difference.
- Against the fixed curve, on two held-out periods and over the whole curve, the formula gains 5 to 8 people per 1,000. Reading the
  opening accounts for 1.4 to 2 of those. That whole-curve gain is small next to the error at one moment.
- Against a fresh average of the previous 90 days, which most creators don't have, for creators it had never seen, it lost one
  period and tied the other. That test used the formula without the opening sheet.
- Creator labels exist only from 2024 on, so "creators it has never seen" is a weaker test for older videos, and a creator's name
  can still appear in other forms in the titles of other groups.
- **It cannot compare two versions of the same video.** It learned from differences between videos. On 41 rewritten openings
  the number fell in 27, rose in 7 and barely moved in 7 ([`eval/delta_numero.py`](../eval/delta_numero.py), exploratory, no real
  retention), so Retina shows no number for the new opening.

Use it as a reference for what to expect, not as a promise.
