# Retina

**Before you publish, see where your audience leaves.**

Retina watches a video draft before it goes to Facebook and tells you whether
its opening (the hook and the first quarter) will lose more people than
similar videos did. Then an agent built on Muse Spark looks at the video,
listens to it, compares it with similar openings that held their audience,
explains why, and proposes one concrete edit. After publishing, it compares
the real retention curve with the predicted one.

Why the opening and not "the exact second": Facebook reports the retention
curve in whole percentage points. Past the first quarter of a video, the drop
between two stretches is almost always 0 or 1 point, so the exact stretch is
rounding noise. We promise what the data supports
([`docs/decisiones.md`](docs/decisiones.md)).

Built by Badabun (Mexico) for the Meta Global AI Developer Hackathon 2026 ·
Startup track · theme *Build for Your World*.

Team: **Marco Zuno** (representative) · **Jossafat Ruvalcaba** (lead developer).

> Retain, never deceive: Retina never suggests what Meta's distribution rules
> penalize (engagement bait, hiding the payoff, miracle cures, unlabeled AI).
> If it sees one in a draft, it flags it. The list lives in
> [`reglas/anzuelos-v1.json`](reglas/anzuelos-v1.json).

## Status

Day 3 of 10 (28-Oct-2026). See [`BUILD-LOG.md`](BUILD-LOG.md) for the dated
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
                        └─► predecir + arranque (own regressions) ─► curve and opening risk vs. similar videos
                                 └─► agente (Spark + tools + validator) ─► card ─► storyboard (Muse Image) ─► panel
```

The agent follows the pattern in Meta's cookbook: **code computes, the model
interprets, a validator checks.** Its tools only read what the services already
computed: `ver_arranque` (risk level and where the opening ends), `ver_tramos`
(what is on screen), `oir` (what is said, with seconds), `buscar_parecidos` (how
similar videos that held their audience open), `medir_lo_prometido` (SAM 3.1 on
the first 3 seconds: does what the title promises appear, from which second and
how big) and `entregar_tarjeta`. The validator rejects the card if it cites a
number that no tool returned, points to a second outside the opening, or
suggests engagement bait; the agent then corrects it. Guards: turn cap, repeated
calls, the project budget cap, and a one-shot fallback (`explicar`). SAM is
never used on people: Meta's acceptable use policy forbids tracking people
across frames, and the code refuses the request before calling the API.

### Service catalog

If a service is not in this table, it does not exist.

| Service | Input → output | Meta model | Cost per call | Status |
|---|---|---|---|---|
| `segmentar` | MP4 → frames per stretch, 24 kHz mono WAV, 480p MP4 | ffmpeg (no model) | 0 | ✅ day 1 |
| `transcribir` | WAV → speech turns with time (JSON) | Muse Voice Transcribe 1.0 | ≈ USD 0.005 / video | ✅ day 2 |
| `describir` | MP4 (file_id) → JSON per stretch, schema `tramo-v1` | Muse Spark 1.3 (Standard) | ≈ USD 0.05 / 100 s | ✅ day 2 |
| `embeber` | 80 frames (2 per stretch) → one 1,024-d vector per stretch | V-JEPA 2 ViT-L (open weights, local GPU) | 0 | ✅ day 2 |
| `predecir` | metadata (+ vectors) → 41-point curve vs. similar videos | own regression | 0 | ✅ day 1 |
| `arranque` | curve of similar videos + metadata → opening risk (high / medium / low) | own regression, saved as JSON | 0 | ✅ day 2 |
| `explicar` | opening + descriptors + speech → why + one edit (one shot, validated) | Muse Spark 1.3 | ≈ USD 0.015 | ✅ day 3 |
| `agente` | case folder → card, with tools and the validator in the loop | Muse Spark 1.3 | ≈ USD 0.02 | ✅ day 3 |
| `sam` | first 3 s + a noun phrase (never a person) → appears?, from when, how big | SAM 3.1 | ≈ USD 0.006 | ✅ day 3 |
| `integridad` | suggestion → blocked rules (rules decide, never the model) | none (code) | 0 | ✅ day 2 |
| `storyboard` | suggestion + 3 reference images → 3 PNG (needs human approval) | Muse Image 1.0 | USD 0.03 | ✅ code |
| `publicar` | approved piece → scheduled post on a **test** page | Graph API (human approval) | 0 | day 7 |
| `escuchar` | post id → real curve + labeled comments | Graph API + Spark | ≈ USD 0.02 | day 7 |
| `evaluar` | held-out videos → metrics with intervals | — | 0 | baseline ✅ day 1 |

Rules live outside the code: [`reglas/`](reglas/). Every API call is logged
(model, tokens, seconds, USD) in `costos.jsonl` by
[`src/retina/meta_api.py`](src/retina/meta_api.py), which also enforces the
project budget cap.

## Try it in one minute (no key, no GPU)

```bash
PYTHONPATH=src python -m retina.demo      # Windows PowerShell: $env:PYTHONPATH="src"; python -m retina.demo
```

Only the Python standard library is needed for the demo.

It opens the review card in your browser, served only on your machine (127.0.0.1), with the example
case in `casos/demo/`. The card answers three questions in plain words: **will the start of my video lose
people, where, and what exactly do I change** (numbered steps with clock times an editor can follow),
plus a check of the first 3 and 10 seconds against Meta's public recommendations, each with its source.
`--caso PATH` opens any other `resultado.json` inside the repo.

The panel is a "liquid glass" interface drawn with WebGL over backgrounds generated with
**Muse Image** (`panel/fondos/`); it falls back to plain CSS when WebGL is not available or the file is
opened with a double click. It only paints text from the JSON (never HTML) and only loads cases from
`casos/` on the same site.

## How to run it with your own key

```bash
pip install -r requirements.txt
# Put MODEL_API_KEY in a .env OUTSIDE the repo (default: un .env fuera del repo),
# or point RETINA_ENV to it. See .env.example.
cd src
python -m retina.gate1 ping                      # one real call to Spark
# Whole pipeline on a published video (the models are trained on private data):
python -m retina.retina VIDEO.mp4 --modelo MODELO.pkl --arranque ARRANQUE.json \
    --salida ../datos/casos/demo --con-api --ya-publicado --voz VOZ.jsonl
python -m retina.agente ../datos/casos/demo --modelo MODELO.pkl --voz VOZ.jsonl
```

The panel reads only `resultado.json`; its contract is in
[`docs/resultado-json.md`](docs/resultado-json.md), with a made-up example in
[`casos/demo/resultado.json`](casos/demo/resultado.json).

Requires Python 3.12 and ffmpeg (on PATH or in `FFMPEG`). Retina is built to review a video *before* you publish it. For company content there is a lock,
on by default (`RETINA_SOLO_PUBLICADOS=1`): only already-published videos go to Meta's API and
`--con-api` requires `--ya-publicado`. If the video is yours, turn it off with
`RETINA_SOLO_PUBLICADOS=0` in your `.env`.

Tests (no API key, no private data): `python -m unittest discover -s tests`.

## Results

Measured on videos the model never saw (Jul–Sep 2026), against today's rule
("average of same format, talent and duration over the previous 90 days").
No number is reported before it is measured, and figures from Badabun's
private data are published only with management's approval.

| Question | What we found |
|---|---|
| Does the predicted curve beat today's rule? | Yes, on all five measures (error at 3 s, 15 s, mid-video, end, whole curve). Figures pending approval. |
| When Retina says the opening risk is "high", does the opening really lose more people? | Clearly more often than the base rate, measured against similar videos *of the same production type* so the type alone can't explain it, and the gap holds within each type. Figures pending approval. |
| Can it point to the exact stretch where people leave? | No. Past the opening it does worse than always guessing the most common stretch, because the curve comes in whole points. We dropped that promise. |
| Does speech help the risk level? | No, measured twice. Speech goes to the agent's explanation instead. |
| Can Spark, watching two real openings of the same type, tell which one loses more people? | No. We ran a blind pairwise judge on clear-difference pairs, each pair in both orders to cancel position bias (with one order it picked the second video every time). When its verdict held in both orders it was no better than a coin flip, and the metadata model beat it on the same pairs. So the risk level stays with the model, and Spark does what it is good at: explaining *where* and *why*, and proposing the edit (`eval/juez_pares.py`). |

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
