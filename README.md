# Retina

**Before you publish, see where your audience leaves.**

Retina watches a video draft before it goes to Facebook, predicts the stretch
where more people will drop off than in similar videos, explains why, and
sketches the fix. After publishing, it compares the real retention curve with
the predicted one.

Built by Badabun (Mexico) for the Meta Global AI Developer Hackathon 2026 ·
Startup track · theme *Build for Your World*.

Team: **Josafat Ruvalcaba** (lead).

> Retain, never deceive: Retina never suggests what Meta's distribution rules
> penalize (engagement bait, hiding the payoff, miracle cures, unlabeled AI).
> If it sees one in a draft, it flags it. The list lives in
> [`reglas/anzuelos-v1.json`](reglas/anzuelos-v1.json).

## Status

Day 1 of 10 (26-Oct-2026). See [`BUILD-LOG.md`](BUILD-LOG.md) for the dated
diary and [`docs/decisiones.md`](docs/decisiones.md) for every decision.

## Architecture

Three decoupled layers: **presentation** (`panel/`, from day 6) ·
**orchestration** (`retina.py`, calls the services in order and versions each
output) · **services** (the table below). Each service takes files or JSON,
returns files or JSON, and does not know who calls it.

```
draft MP4 ─► segmentar ─► 40 stretches aligned to the 41-point curve + WAV + light MP4
               ├─► transcribir  (Muse Voice Transcribe)  speech turns, silences
               ├─► embeber      (V-JEPA 2, open weights, our GPU)  one vector per stretch
               └─► describir    (Muse Spark 1.3, Files API, strict JSON)  what is on screen
                        └─► predecir (own regression) ─► risky stretch vs. similar videos
                                 └─► explicar (Spark) ─► storyboard (Muse Image) ─► panel
```

### Service catalog

If a service is not in this table, it does not exist.

| Service | Input → output | Meta model | Cost per call | Status |
|---|---|---|---|---|
| `segmentar` | MP4 → frames per stretch, 24 kHz mono WAV, 480p MP4 | ffmpeg (no model) | 0 | ✅ day 1 |
| `transcribir` | WAV → speech turns with time (JSON) | Muse Voice Transcribe 1.0 | ≈ USD 0.005 / video | ✅ code, pending key |
| `describir` | MP4 (file_id) → JSON per stretch, schema `tramo-v1` | Muse Spark 1.3 (Standard) | measured day 1 | ✅ code, pending key |
| `embeber` | frames per stretch → vector per stretch | V-JEPA 2 (local) | 0 | day 2 |
| `predecir` | vectors + descriptors + metadata → 41-point curve + risky stretch | own regression | 0 | day 3 |
| `explicar` | stretch + descriptors + bait list → explanation + suggestion | Muse Spark 1.3 | ≈ USD 0.01 | day 4 |
| `storyboard` | suggestion + 3 reference images → 3 PNG | Muse Image 1.0 | USD 0.03 | day 4 |
| `publicar` | approved piece → scheduled post on a **test** page | Graph API (human approval) | 0 | day 7 |
| `escuchar` | post id → real curve + labeled comments | Graph API + Spark | ≈ USD 0.02 | day 7 |
| `evaluar` | held-out videos → metrics with intervals | — | 0 | day 2+ |

Rules live outside the code: [`reglas/`](reglas/). Every API call is logged
(model, tokens, seconds, USD) in `costos.jsonl` by
[`src/retina/meta_api.py`](src/retina/meta_api.py), which also enforces the
project budget cap.

## How to run it with your own key

```bash
pip install -r requirements.txt
# Put MODEL_API_KEY in a .env OUTSIDE the repo (default: un .env fuera del repo),
# or point RETINA_ENV to it. See .env.example.
cd src
python -m retina.segmentar VIDEO.mp4 --salida ../datos/casos/demo
python -m retina.gate1 ping                      # one real call to Spark
python -m retina.gate1 video ../datos/casos/demo   # token count + transcription
python -m retina.describir ../datos/casos/demo     # JSON per stretch
```

Requires Python 3.10+ and ffmpeg (on PATH or in `FFMPEG`).

## Results

Measured on videos the model never saw (Jul–Sep 2026), against today's
rule ("average of same format, talent and duration over the previous 90 days").
No number is reported before it is measured.

| Metric | Baseline | Target | Retina |
|---|---|---|---|
| Mean absolute error at 15 s | to be measured | ≤ 9.3 pts | — |
| Error at 3 s | to be measured | ≤ baseline | — |
| Error at mid-video | to be measured | ≤ baseline | — |
| Spearman, rank of retention | to be measured | ≥ 0.50 | — |
| Hit on the stretch of largest abnormal drop (exact / ±1) | to be measured | +10 pts | — |

## Prior infrastructure and data (not built during the event)

Declared here so the jury can tell what is new. None of it appears in the demo
video as event work.

- A list of published videos paired with their 41-point Facebook retention
  curve, built before 26-Oct-2026. Stays on Badabun's server; never in this repo.
- Badabun's existing Graph API reader and servers.
- Internal findings measured before the event (e.g. effect of introducing the
  host before the hook). Retina must rediscover or beat them.

Everything in this repository was written from 26-Oct-2026 on.

## What's next

To be written on day 10.

## License

[MIT](LICENSE).
