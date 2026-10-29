# Retina

**Before you publish, see where your audience leaves.**

Retina reviews a video draft before it goes to Facebook and tells you whether
its opening (the hook and the first quarter) will lose more people than
similar videos did. Muse Spark 1.3 watches the video and Muse Voice Transcribe
listens to it; then an agent running on **Muse Spark Open**, Meta's open-weight
model, investigates what they found, compares it with similar openings that
held their audience, explains why, and proposes one concrete edit with steps an
editor can follow. **Muse Image** draws what the new opening would look like.
For videos that are already published, we lay the real retention curve over the
predicted one to check it ([`eval/prediccion_vs_real.py`](eval/prediccion_vs_real.py)).

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

## Meta models in Retina

| Step | Model | Where it runs | What it does |
|---|---|---|---|
| The agent (main step) | **Muse Spark Open** (open weights) | Baseten Model API | Investigates the opening with five tools, writes the card, fixes it when the validator objects |
| Safety net | Muse Spark 1.3 | Meta Model API | Takes over a case only if the Spark Open agent does not close it (0 of 50 in our run) |
| Watching | Muse Spark 1.3 (Files API) | Meta Model API | Describes what is on screen in each stretch (strict JSON) |
| Listening | Muse Voice Transcribe 1.0 | Meta Model API | Speech with timestamps, and silences |
| Checking the promise | SAM 3.1 | Meta Model API | Does what the title promises appear in the first 3 s, from which second, how big (never on people) |
| Drawing the fix | Muse Image 1.0 | Meta Model API | A 3-frame storyboard of the suggested opening, shown in the panel; also the panel backgrounds |
| Video features (tried) | V-JEPA 2 (open weights) | Our GPU | One vector per stretch. Measured: it does not improve the risk level, so the level does not depend on it |

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
               ├─► embeber      (V-JEPA 2, open weights, our GPU; optional)  one vector per stretch
               └─► describir    (Muse Spark 1.3, Files API, strict JSON)  what is on screen
                        └─► predecir + arranque (own regressions) ─► curve and opening risk vs. similar videos
                                 └─► agente (Spark Open + tools + validator; Spark 1.3 rescues) ─► card ─► storyboard (Muse Image) ─► panel
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
| `embeber` | 80 frames (2 per stretch) → one 1,024-d vector per stretch | V-JEPA 2 ViT-L (open weights, local GPU) | 0 | ✅ day 2 · optional: no gain on the risk level |
| `predecir` | metadata (+ vectors) → 41-point curve vs. similar videos | own regression | 0 | ✅ day 1 |
| `arranque` | curve of similar videos + metadata → opening risk (high / medium / low) | own regression, saved as JSON | 0 | ✅ day 2 |
| `explicar` | opening + descriptors + speech → why + one edit (one shot, validated; the agent's fallback) | Muse Spark Open or 1.3 (`RETINA_MOTOR`) | ≈ USD 0.03 | ✅ day 3 |
| `agente` | case folder → card, with tools and the validator in the loop | **Muse Spark Open** (open weights, Baseten); Muse Spark 1.3 rescues | ≈ USD 0.04 | ✅ day 3 |
| `sam` | first 3 s + a noun phrase (never a person) → appears?, from when, how big | SAM 3.1 | ≈ USD 0.006 | ✅ day 3 |
| `integridad` | suggestion → blocked rules (rules decide, never the model) | none (code) | 0 | ✅ day 2 |
| `storyboard` | suggestion → 3 illustrations of the new opening, shown in the panel (needs human approval) | Muse Image 1.0 | USD 0.03 | ✅ day 3 |
| `publicar` | approved piece → scheduled post on a **test** page | Graph API (human approval) | 0 | not built (after the event) |
| `escuchar` | post id → real curve + labeled comments | Graph API + Spark | ≈ USD 0.02 | not built (after the event) |
| `evaluar` | held-out videos → metrics with intervals | — | 0 | baseline ✅ day 1 |

Rules live outside the code: [`reglas/`](reglas/). Every API call is logged
(model, tokens, seconds, USD) in `costos.jsonl` by
[`src/retina/meta_api.py`](src/retina/meta_api.py), which also enforces the
project budget cap.

## Try it in one minute (no key, no GPU)

```bash
PYTHONPATH=src python -m retina.demo      # Windows PowerShell: $env:PYTHONPATH="src"; python -m retina.demo
```

Only the Python standard library is needed for the demo. The interface is in Spanish and English: use the **English** button in the header,
or open `/panel/?lang=en` (the made-up example is translated too, in `casos/demo-en/`).

It opens the review card in your browser, served only on your machine (127.0.0.1), with the example
case in `casos/demo/`. The card answers three questions in plain words: **will the start of my video lose
people, where, and what exactly do I change** (numbered steps with clock times an editor can follow),
plus a check of the first 3 and 10 seconds against Meta's public recommendations, each with its source,
and a 3-frame storyboard of the new opening drawn with **Muse Image**. It also says which model wrote
the card. `--caso PATH` opens any other `resultado.json` inside the repo.

The panel is a "liquid glass" interface drawn with WebGL over backgrounds generated with
**Muse Image** (`panel/fondos/`); it falls back to plain CSS when WebGL is not available or the file is
opened with a double click. It only paints text from the JSON (never HTML) and only loads cases from
`casos/` on the same site.

## How to run it with your own key

```bash
pip install -r requirements.txt
# Put MODEL_API_KEY in a .env OUTSIDE the repo (default: un .env fuera del repo),
# or point RETINA_ENV to it. See .env.example.
# The agent runs on Muse Spark Open by default: add BASETEN_API_KEY too. Without it,
# Spark 1.3 takes every case. RETINA_MOTOR=api uses only Spark 1.3.
cd src
python -m retina.gate1 ping                      # one real call to Spark
# Whole pipeline on a published video (the models are trained on private data):
python -m retina.retina VIDEO.mp4 --modelo MODELO.pkl --arranque ARRANQUE.json \
    --salida ../datos/casos/demo --con-api --ya-publicado --voz VOZ.jsonl
python -m retina.agente ../datos/casos/demo --modelo MODELO.pkl --voz VOZ.jsonl
```

**From the browser (local prototype).** `python -m retina.app --casos CASES_DIR --modelo PREDECIR.pkl
--arranque ARRANQUE.json --voz VOZ.jsonl` opens a page where you drop an MP4 and fill in four fields (it
fills them from a file name like `2026-01-15 XYZ0000001 TALENT Title.mp4`). The same pipeline runs in the
background, one video at a time, and the card opens when it is ready (about 3 minutes). It listens only on
127.0.0.1, accepts uploads only from its own page, only MP4, and keeps the published-only lock.
`python -m retina.demo --casos CASES_DIR --galeria` lists every reviewed case in that folder (it needs an
`indice.json`).

The panel reads only `resultado.json`; its contract is in
[`docs/resultado-json.md`](docs/resultado-json.md), with a made-up example in
[`casos/demo/resultado.json`](casos/demo/resultado.json).

Requires Python 3.12 and ffmpeg (on PATH or in `FFMPEG`; on Windows, `winget install Gyan.FFmpeg`).
V-JEPA 2 and the local Whisper script are optional and need `pip install -r requirements-gpu.txt`
and a GPU; without them the pipeline still runs. Retina is built to review a video *before* you publish it. For company content there is a lock,
on by default (`RETINA_SOLO_PUBLICADOS=1`): only already-published videos go to Meta's API and
`--con-api` requires `--ya-publicado`. If the video is yours, turn it off with
`RETINA_SOLO_PUBLICADOS=0` in your `.env`.

Tests (no API key, no private data): `pip install -r requirements.txt`, then
`python -m unittest discover -s tests`.

## Open weights: the agent runs on Muse Spark Open

The main step of Retina, the agent that investigates the opening and writes the
card the editor sees, runs on **Muse Spark Open** (`meta-models/muse-spark-open-1026`,
served by Baseten's Model API), and it is the default. It gets the same instructions
([`skills/agente.md`](skills/agente.md)), the same five tools and the same
validator as Muse Spark 1.3, through Chat Completions with tool calling
([`src/retina/agente.py`](src/retina/agente.py), `ConSparkOpen`). If its loop
does not close a case, Muse Spark 1.3 takes over that case
(`RETINA_MOTOR=abierto+api`).

Measured on the same 50 videos as the Spark 1.3 agent
([`eval/casos_agente.py`](eval/casos_agente.py)). They were published from July to
September 2026, after the models' training cut, but we also used them to tune the
agent's instructions, so read this as a comparison between the two models, not as a
clean test. One run each.

| Same 50 videos | Agent on Muse Spark 1.3 | Agent on **Muse Spark Open** |
|---|---|---|
| Cases closed by the agent itself | 50 | **50** (Spark 1.3 rescued 0) |
| Cards the validator sent back, then the agent fixed on its own | 16 | 42 |
| Average turns | 6.2 | 5.6 |
| Times it asked SAM 3.1 to check the promise | 6 | 14 |
| Risky openings left without a suggestion | 0 | 0 |
| Cards with steps for the editor | 38 | 37 |
| Engagement bait already in the video | (reference) | Same number caught; each model caught one the other missed |
| Cost per video (agent only) | USD 0.029 | USD 0.038 |

Spark Open writes longer texts and reaches for phrases our rules block more
often, so the validator sends its first card back more often (mostly a text over
220 characters or an engagement-bait phrase). It fixes them inside the loop: the
editor only sees cards that passed.

How we got there, honestly: written in one shot, without tools, Spark Open is
clearly weaker than Spark 1.3 (28 of 50 cards passed the validator on the first
try, against 46; [`eval/casos_spark_open.py`](eval/casos_spark_open.py)), and
raising its reasoning effort did not help there (22 of 50). What closed the gap
was letting it work as an agent: with tools to look again and a validator that
returns its objections inside the loop, it reached Spark 1.3's coverage. In the
agent it runs with `reasoning_effort: high`, which Baseten honors.

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
| Do the agent's tools make the card better than one shot? | Not that we can show. A blind judge (Muse Spark 1.3, each pair in both orders) preferred the one-shot card in 27 of 39 firm pairs and the agent's in 12. The judge only sees the data the one-shot card had, so what the agent found with its tools can look invented to it. The rule was written before measuring ([`eval/juez_tarjetas.py`](eval/juez_tarjetas.py), [`docs/decisiones.md`](docs/decisiones.md)). |
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

### What is not a Meta model

Declared so stage 1 can check it. Every model *called* during a review is Meta's
(table above). Besides them:

- **The risk level and the curve** come from two ridge regressions fitted on Badabun's
  published curves: a fixed linear formula (features × coefficients) applied in code.
- **Transcripts of the archive.** During the event we transcribed our past videos once,
  offline, with Whisper (`src/retina/transcribir_local.py`). No Whisper runs during a review;
  the agent's `buscar_parecidos` tool reads those stored transcripts to show how similar
  videos opened. A new video is always transcribed with Muse Voice Transcribe.
- **ffmpeg** cuts the video; it is not a model.

## What's next

- Inside Badabun: run Retina on a company server behind the intranet login, so editors upload
  a draft and get the card without a command line (today `retina.app` is a local prototype).
- Close the loop after publishing (`escuchar`): read the real curve and compare it with the
  prediction automatically, and measure whether applying the suggested edit keeps more people.
- Re-fit the risk model every month with the newest curves.

## License

[MIT](LICENSE).
