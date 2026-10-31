# How Retina is built

Three decoupled layers: **presentation** (`panel/`), **orchestration** (`retina.py` for the review, `apertura.py` for the fix) and
**services** (the table below). Each service takes files or JSON, returns files or JSON, and does not know who calls it.

```
draft MP4 ─► segmentar ─► 40 stretches + WAV + light MP4
               ├─► transcribir  (Muse Voice Transcribe)  speech turns, silences
               ├─► describir    (Muse Spark 1.3, Files API, strict JSON)  what is on screen
               ├─► ficha        (Muse Spark Open)  how the opening starts
               ├─► sam          (Muse Spark 1.3 + SAM 3.1)  does the title's promise show in the first 3 s?
               ├─► normas       (Muse Spark 1.3 + code)  possible breaches of Facebook's rules, with evidence
               ├─► número       (fixed formula, docs/numero.md)  how many of 100 may stay
               └─► explicar     (Muse Spark Open, validator; Muse Spark 1.3 rescues) ─► card ─► panel

press «Fix the opening» ─► apertura:
    Muse Spark Open writes ─► rules in code ─► Muse Image draws frame 1 ─► SAM 3.1 looks for the promise
          ▲                       │ fails                                        │ fails
          └───────────────────────┴──── exact list of failures, up to 2 times ───┘
                                  │ all pass
                                  └─► Muse Image draws frames 2 and 3 ─► before and after in the panel
```

## Service catalog

If a service is not in this table, it does not exist.

| Service | Input → output | Meta model | Cost per call | Status |
|---|---|---|---|---|
| `segmentar` | MP4 → frames per stretch, 24 kHz mono WAV, 480p MP4 | ffmpeg (no model) | 0 | ✅ |
| `transcribir` | WAV → speech turns with time (JSON) | Muse Voice Transcribe 1.0 | ≈ USD 0.005 / video | ✅ |
| `describir` | MP4 (file_id) → JSON per stretch, schema `tramo-v1` | Muse Spark 1.3 (Standard) | ≈ USD 0.05 / 100 s | ✅ |
| `embeber` | 80 frames (2 per stretch) → one 1,024-d vector per stretch | V-JEPA 2 ViT-L (open weights, local GPU) | 0 | research: no gain on the risk level |
| `apertura` | title + what was seen and said → new opening, rules, frames, SAM check, up to 2 corrections | **Muse Spark Open**, Muse Image 1.0, SAM 3.1 | ≈ USD 0.05 to 0.25 | ✅ · the core of Retina |
| `normas` | what is seen and said → possible breaches of 18 public rules, with second and evidence | Muse Spark 1.3 + code | ≈ USD 0.01 | ✅ |
| `publico` | title, speech and opening sheet → 41-point curve vs. videos of the same length | small fitted formula, [`numero.md`](numero.md) | 0 | ✅ |
| `predecir` | metadata (+ vectors) → 41-point curve vs. similar videos | own regression, private layer | 0 | research |
| `arranque` | curve of similar videos + metadata → opening risk (high / medium / low) | own regression, saved as JSON | 0 | research: the traffic light is not shown |
| `explicar` | opening + descriptors + speech → why + one edit (one shot, validated; the agent's fallback) | Muse Spark Open or 1.3 (`RETINA_MOTOR`) | ≈ USD 0.03 | ✅ |
| `agente` | case folder → card, with tools and the validator in the loop | **Muse Spark Open** (open weights, Baseten); Muse Spark 1.3 rescues | ≈ USD 0.04 | ✅ |
| `sam` | first 3 s or a drawn frame + a noun phrase (never a person) → appears?, from when, how big | SAM 3.1 | ≈ USD 0.01 | ✅ |
| `traducir` | a review → the same review in the other panel language, once, with numbers checked | Muse Spark 1.3 | less than USD 0.01 | ✅ |
| `integridad` | suggestion → blocked rules (rules decide, never the model) | none (code) | 0 | ✅ |
| `storyboard` | a card's suggestion → 3 illustrations, from the command line (needs human approval) | Muse Image 1.0 | USD 0.03 | ✅ |
| `publicar` | approved piece → scheduled post on a **test** page | Graph API (human approval) | 0 | not built (after the event) |
| `escuchar` | post id → real curve + labeled comments | Graph API + Spark | ≈ USD 0.02 | not built (after the event) |
| `evaluar` | held-out videos → metrics with intervals | — | 0 | baseline ✅ |

Rules live outside the code: [`reglas/`](../reglas/). Every API call is logged (model, tokens, seconds, USD) in your own log
(`mis-revisiones/costos.jsonl`, outside the repo) by [`src/retina/meta_api.py`](../src/retina/meta_api.py), which also enforces a budget cap.

## The agent

The company version follows the pattern in Meta's cookbook: **code computes, the model interprets, a validator checks.** Its tools only
read what the services already computed: `ver_arranque` (risk level and where the opening ends), `ver_tramos` (what is on screen), `oir`
(what is said, with seconds), `buscar_parecidos` (how similar videos that held their audience open), `medir_lo_prometido` (SAM 3.1 on the
first 3 seconds) and `entregar_tarjeta`. The validator rejects the card if it cites a number no tool returned, points to a second
outside the opening, or suggests engagement bait; the agent then corrects it. Guards: turn cap, repeated calls, the project budget cap,
and a one-shot fallback (`explicar`).

The card runs on **Muse Spark Open** (`meta-models/muse-spark-open-1026`, served by Baseten's Model API) by default, with the same
instructions ([`skills/agente.md`](../skills/agente.md)), tools and validator as Muse Spark 1.3, through Chat Completions with tool calling
([`src/retina/agente.py`](../src/retina/agente.py), `ConSparkOpen`). If its loop does not close a case, Muse Spark 1.3 takes over
(`RETINA_MOTOR=abierto+api`). In the agent it runs with `reasoning_effort: high`.

The public version writes the card in one pass with the same validator, because the agent's best tool looks up a company's own past
videos. The card says which model wrote it. A company can add its own layer on top (its creators, its history, its transcripts) with a
private model; that layer is not part of this entry.

SAM is never used on people: Meta's acceptable use policy forbids tracking people across frames. The code only accepts objects from a
closed list and refuses any person word, before calling the API.

## The app

The upload screen takes optionally who is on camera and a production code (a date, code or name at the start of the file name, like
`2026-01-15 XYZ0000001 Title.mp4`, is filled in; useful only to a company with its own private model). The pipeline runs in the
background, one video at a time, and the panel shows what each model is doing and opens the card when it is ready (3 to 5 minutes). The app listens only on 127.0.0.1,
accepts uploads only from its own page and only video files: MP4 and MOV are used as they are; WebM, MKV, AVI and FLV are converted to MP4
with ffmpeg. It honours the published-only lock (`RETINA_SOLO_PUBLICADOS`) set in the `.env`.

**Compare two versions.** On the same screen, «Compare two versions» takes two cuts of the same video. Retina reviews each one and then
`retina.comparar` asks Muse Spark Open (Muse Spark 1.3 as rescue) which start is stronger and why, from what Retina saw in each start. It
judges in both orders and only declares a stronger start when both orders agree; otherwise it says it is a tie. This is Spark's reading
of the two starts, not a prediction of which one loses fewer people: Spark was no better than a coin flip at that. The retention numbers
barely move between two cuts of the same video. Output: `comparacion.json` in version B's folder (`python -m retina.comparar CASE_A CASE_B`).

Every card lists what works, what is weak and up to three optional improvements (`lo_bueno`, `lo_flojo`, `mejoras_opcionales`), checked by
the same validator as the main change.

The panel reads only `resultado.json`; its contract is in [`resultado-json.md`](resultado-json.md), with a made-up example in
[`casos/demo/resultado.json`](../casos/demo/resultado.json). It paints text from the JSON, never HTML, and only loads cases from `casos/` on
the same site. It is a "liquid glass" interface drawn with WebGL over backgrounds generated with **Muse Image** (`panel/fondos/`), and
falls back to plain CSS when WebGL is not available.

V-JEPA 2 and the local Whisper script are optional and need `pip install -r requirements-gpu.txt` and a GPU; without them the pipeline
still runs.

## Reproducing our measurements

The measurements in `eval/` and the private model need Badabun's private archive, which is not in this repository.
`python -m retina.publico` rebuilds the public brain from such a base. Without that data you can still read every rule in
[`decisiones.md`](decisiones.md) and run the tests.

## What's next

- Inside a company: run Retina on a server behind its login, so editors upload a draft and get the card without a command line.
- Close the loop after publishing (`escuchar`): read the real curve, compare it with the prediction, and measure whether a new opening
  keeps more people.
- Re-fit the number every month with the newest curves.
