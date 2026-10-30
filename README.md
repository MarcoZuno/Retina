# Retina

**Retina estimates how many people will stay, then rewrites your opening and checks the fix before you publish.**

![Retina's before and after for a made-up example video: the draft opens with a greeting and no bread in sight; the new opening shows the bread from the first frame, with the list of checks it passed](docs/img/retina-example-card.jpg)

*The picture above is a made-up example (no real video), with drawings by Muse Image. Open it yourself in one
minute, with no key: see "Try it in one minute" below.*

**What makes it different.** Retina starts from retention, using what about 30,000 real videos taught it about when people leave. Then
it acts: a tool that only reads a video stops at a description or a grade, and Retina's output is a new opening you can watch and hear,
and its core is a rule engine and a verification loop around Meta's models: the rules run in code, after the model, and send the
work back with the exact list of what failed. SAM 3.1 then has to find what the title promises inside the frame Muse Image drew. One
prompt to one model cannot do this.

It also checks the whole video against Facebook's public rules, with the second and the words behind each warning.

How the opening gets fixed:

1. **Watch and listen.** Muse Spark 1.3 describes what is on screen and Muse Voice Transcribe writes down what is said.
2. **Rewrite.** **Muse Spark Open**, Meta's open-weight model, writes a new opening that brings the title's promise to
   the front. The title itself is never touched: it belongs to whoever wrote the script.
3. **Check the words.** Fixed code rules, not a model, read the result: none of the engagement bait Meta's distribution
   rules penalize, nothing that touches logos, legal notices or credits, every number and name must come from the video,
   the title's topic in the first sentence, and a length that fits 10 to 15 seconds.
4. **Draw it.** **Muse Image** draws the first frame.
5. **Check the picture.** **SAM 3.1** looks for what the title promises in that frame. Muse Spark 1.3 picks it from a
   closed list of objects and places, never people.
6. **Correct.** If anything fails, Spark Open receives the exact list of failures and tries again, up to twice. What does
   not pass never reaches you.
7. **Before and after.** You see your opening next to the new one, press play to watch the frames and hear the new words in your
   browser's voice, and see every check it passed.

Three limits we say out loud. **The number is a modest reference**, not a promise: it barely beats the average for videos
of the same length, and it cannot compare two versions of one video, so Retina shows no number for the new opening. **The
"after" is a sketch** (voice and drawings), not a filmed video. **Retina does not promise that the new opening keeps more
people watching**: we never measured that. The rules check is a first look, not a guarantee: Meta makes the final call.

Built by Badabun (Mexico) for the Meta Global AI Developer Hackathon 2026 ·
Startup track · theme *Build for Your World*.

Team: **Marco Zuno** (representative) · **Jossafat Ruvalcaba** (lead developer).

## What we measured, and what happened (sealed rules, in words)

Every idea entered with its pass/fail rule written down **before** we measured, in
[`docs/decisiones.md`](docs/decisiones.md), and the later ones were sealed with a git commit before measuring. We report
what failed as well as what passed. The numbers come from a private Facebook archive of a large page in
Mexico and stay out of this repository, so here they are in words.

| Question | Rule written first | Result |
|---|---|---|
| Can Retina rewrite an opening that keeps the title's promise and breaks no rule? (first test, 50 videos) | At least 15 of 18 openings with a visible promise pass every check in 2 corrections or fewer, 26 of the other 32 pass, and SAM rejects 9 of 10 trap frames | **Did not pass.** 10 of 18. The other two parts passed (31 of 32, and 10 of 10). SAM did not know words like "tortilla" even when the drawing showed one |
| The same question after calibrating SAM's vocabulary (second test, 30 videos never used for this) | At least 24 of 30 pass everything and SAM rejects 9 of 10 trap frames | **Passed**: 29 of 30, 23 of them on the first try, and SAM rejected 9 of 10 traps. Details under Results |
| Can the predicted curve beat today's rule (the average of videos of the same duration and creator over the previous 90 days)? | Beat it on error at 3 s, 15 s, mid-video, end and whole curve | **Passed** on videos the model had not seen |
| Does the "high / medium / low" opening level pick out openings that really lose more people? | Better than the base rate, against videos of the same production type | **Passed**: openings flagged "high" lost more people than the base rate |
| Can we point to the exact stretch where people leave? | Beat always guessing the most common stretch | **Did not pass.** The curve comes in whole points, so past the opening it is rounding noise. We dropped the promise |
| Does speech improve the risk level? | Improve it on held-out videos | **Did not pass**, measured twice. Speech goes to the explanation instead |
| Does looking at the video (frame features, audio, pace) improve the risk level? | Improvement above zero, with a confirmation period set in advance | **Did not pass** in either period |
| Can Spark, watching two openings, say which loses more people? | Better than a coin flip, each pair judged in both orders | **Did not pass.** It was no better than a coin flip and the data model beat it |
| Do the agent's tools make the card better than one pass? | The agent wins at least 60 % of firm pairs in a blind comparison | **Did not pass.** The blind judge preferred the one-pass card, so the public version writes the card in one pass |
| Does Retina work for a creator it has never seen? | Lower error on the whole curve and better ordering at 15 s, with intervals that do not overlap | **First period did not pass.** We then changed the comparison (a paired difference per video), which makes that period a hint, not a result. A second period, with the new rule written before running, **passed**: a small, real improvement |
| Does the public brain file (no video, no creator names) hold up? | Beat the fixed curve by duration on a period it had not seen | **Passed** its rule on Jan-Jun 2026. In later checks against the plain average for its duration it lost in Jul-Dec 2025 and only tied in Jan-Jun 2026 |
| Does reading the opening (a fixed sheet filled by Muse Spark Open) improve the number? | Better in both of two periods | **Passed**, with the rule sealed by a commit before measuring |
| Does a better opening go with more reach on Facebook? | A positive relation, in two separate periods and then on videos predicted before publishing | **Passed** (a relation, not proof of cause) |
| Does the traffic light work for creators it has never seen (v1)? | "High" for 15-35 % of videos, clearly above the base rate, "low" below it, in two periods | **Did not pass**: it flagged too many videos as "high" in one period. **The public mode shows no traffic light.** |
| A second traffic light (v2)? | Same rule as v1 | It passed, but it was written after seeing v1 fail and tested on periods already used several times. By our own rule it counts as exploratory and **is not in the public mode** |

> Retain, never deceive: Retina never suggests what Meta's distribution rules
> penalize (engagement bait, hiding the payoff, miracle cures, unlabeled AI).
> If it sees one in a draft, it flags it. The list lives in
> [`reglas/anzuelos-v1.json`](reglas/anzuelos-v1.json).

## Meta models in Retina

Every AI model Retina calls while it runs is a Meta model. The one exception is a small formula, explained below the table.

| Step | Model | Where it runs | What it does |
|---|---|---|---|
| Rewriting the opening (main step) | **Muse Spark Open** (open weights) | Baseten Model API | Writes the new first 10 to 15 seconds and the three frames, and fixes them when a check fails. Without a Baseten key, Muse Spark 1.3 does it |
| Drawing it | **Muse Image 1.0** | Meta Model API | Draws the first frame and, once everything passes, the other two |
| Checking the promise | Muse Spark 1.3 + **SAM 3.1** | Meta Model API | Spark picks what the title promises from a closed list of objects and places (never people); SAM looks for it in the first 3 s of the draft and in the first drawn frame |
| Checking Facebook's rules | Muse Spark 1.3 | Meta Model API | Reads the whole video against a closed list of 18 public Meta rules; code drops any warning without real evidence from the video |
| Watching | Muse Spark 1.3 (Files API) | Meta Model API | Describes what is on screen in each stretch (strict JSON), in the reviewer's language |
| Listening | Muse Voice Transcribe 1.0 | Meta Model API | Speech with timestamps, and silences |
| Reading the opening | **Muse Spark Open** (open weights) | Baseten Model API | Reads the title and the first words and fills a fixed sheet: hook tactic, whether the speaker introduces themselves before the topic, clarity, curiosity, emotion |
| Writing the card | **Muse Spark Open** (open weights) | Baseten Model API | What works and what is weak in the draft, checked by the same validator. Muse Spark 1.3 takes over only if Spark Open does not pass |
| The agent (with a company's private layer) | Muse Spark Open | Baseten Model API | Same card, plus tools to look up how that company's similar videos opened (needs its private history) |

**The reference number is a small fitted formula, not an AI call.** It is a ridge regression fitted offline on the retention
data of a large Facebook page in Mexico, and at runtime it is a JSON file of fixed weights that plain Python multiplies and adds.
It adjusts the average curve for the video's length; it writes nothing and decides nothing. The fit: ridge regression in closed form
with λ = 300, from 1,703 inputs to the 41 points of the curve, on about 30,000 videos without eligibility, out-of-scope topics or serious
topics. The fixed weights are in [`modelos/retina-publico.json`](modelos/retina-publico.json) and the full method and data description
are in [`docs/numero.md`](docs/numero.md). The organizers ruled on 30-Oct-2026 that ridge coefficients are acceptable when the README
explains the layer, with its fitting details and its weights in the repo. `RETINA_SOLO_MODELOS_META=1` turns it off and the rest of
Retina works the same. Whisper ran offline only, to build the training set; it never runs in the app.

## Status

Entry for the Meta Global AI Developer Hackathon (due 4-Nov-2026). See [`BUILD-LOG.md`](BUILD-LOG.md) for the dated
diary and [`docs/decisiones.md`](docs/decisiones.md) for every decision.

## Architecture

Three decoupled layers: **presentation** (`panel/`) ·
**orchestration** (`retina.py` for the review, `apertura.py` for the fix) · **services** (the table below). Each service
takes files or JSON, returns files or JSON, and does not know who calls it.

```
draft MP4 ─► segmentar ─► 40 stretches + WAV + light MP4
               ├─► transcribir  (Muse Voice Transcribe)  speech turns, silences
               ├─► describir    (Muse Spark 1.3, Files API, strict JSON)  what is on screen
               ├─► ficha        (Muse Spark Open)  how the opening starts
               ├─► sam          (Muse Spark 1.3 + SAM 3.1)  does the title's promise show in the first 3 s?
               ├─► normas       (Muse Spark 1.3 + code)  possible breaches of Facebook's rules, with evidence
               ├─► número       (fixed formula, docs/numero.md)  how many of 100 may stay
               └─► explicar     (Muse Spark Open, validator; Muse Spark 1.3 rescues) ─► card ─► panel

press «Fix my opening» ─► apertura:
    Muse Spark Open writes ─► rules in code ─► Muse Image draws frame 1 ─► SAM 3.1 looks for the promise
          ▲                       │ fails                                        │ fails
          └───────────────────────┴──── exact list of failures, up to 2 times ───┘
                                  │ all pass
                                  └─► Muse Image draws frames 2 and 3 ─► before and after in the panel
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
across frames. The code only accepts objects from a closed list and refuses any person word, before calling the API.

### Service catalog

If a service is not in this table, it does not exist.

| Service | Input → output | Meta model | Cost per call | Status |
|---|---|---|---|---|
| `segmentar` | MP4 → frames per stretch, 24 kHz mono WAV, 480p MP4 | ffmpeg (no model) | 0 | ✅ |
| `transcribir` | WAV → speech turns with time (JSON) | Muse Voice Transcribe 1.0 | ≈ USD 0.005 / video | ✅ |
| `describir` | MP4 (file_id) → JSON per stretch, schema `tramo-v1` | Muse Spark 1.3 (Standard) | ≈ USD 0.05 / 100 s | ✅ |
| `embeber` | 80 frames (2 per stretch) → one 1,024-d vector per stretch | V-JEPA 2 ViT-L (open weights, local GPU) | 0 | research: no gain on the risk level |
| `apertura` | title + what was seen and said → new opening, rules, frames, SAM check, up to 2 corrections | **Muse Spark Open**, Muse Image 1.0, SAM 3.1 | ≈ USD 0.05 to 0.25 | ✅ · the core of Retina |
| `normas` | what is seen and said → possible breaches of 18 public rules, with second and evidence | Muse Spark 1.3 + code | ≈ USD 0.01 | ✅ |
| `publico` | title, speech and opening sheet → 41-point curve vs. videos of the same length | small fitted formula, [`docs/numero.md`](docs/numero.md) | 0 | ✅ |
| `predecir` | metadata (+ vectors) → 41-point curve vs. similar videos | own regression, private layer | 0 | research |
| `arranque` | curve of similar videos + metadata → opening risk (high / medium / low) | own regression, saved as JSON | 0 | research: the traffic light is not shown |
| `explicar` | opening + descriptors + speech → why + one edit (one shot, validated; the agent's fallback) | Muse Spark Open or 1.3 (`RETINA_MOTOR`) | ≈ USD 0.03 | ✅ |
| `agente` | case folder → card, with tools and the validator in the loop | **Muse Spark Open** (open weights, Baseten); Muse Spark 1.3 rescues | ≈ USD 0.04 | ✅ |
| `sam` | first 3 s or a drawn frame + a noun phrase (never a person) → appears?, from when, how big | SAM 3.1 | ≈ USD 0.01 | ✅ |
| `integridad` | suggestion → blocked rules (rules decide, never the model) | none (code) | 0 | ✅ |
| `storyboard` | a card's suggestion → 3 illustrations, from the command line (needs human approval) | Muse Image 1.0 | USD 0.03 | ✅ |
| `publicar` | approved piece → scheduled post on a **test** page | Graph API (human approval) | 0 | not built (after the event) |
| `escuchar` | post id → real curve + labeled comments | Graph API + Spark | ≈ USD 0.02 | not built (after the event) |
| `evaluar` | held-out videos → metrics with intervals | — | 0 | baseline ✅ |

Rules live outside the code: [`reglas/`](reglas/). Every API call is logged
(model, tokens, seconds, USD) in your own log (`mis-revisiones/costos.jsonl`, outside the
repo) by [`src/retina/meta_api.py`](src/retina/meta_api.py), which also enforces a budget cap. Our
team's log is [`docs/costos-equipo.jsonl`](docs/costos-equipo.jsonl).

## Try it in one minute (no key, no GPU)

```bash
PYTHONPATH=src python -m retina.demo      # Windows PowerShell: $env:PYTHONPATH="src"; python -m retina.demo
```

Only the Python standard library is needed for the demo. The interface is in Spanish and English: use the **English** button in the header,
or open `/panel/?lang=en` (the made-up example is translated too, in `casos/demo-en/`).

It opens the example in your browser, served only on your machine (127.0.0.1), from `casos/demo/`: how many of 100 people may
stay, the opening before and after with every check it passed, the check against Facebook's rules, and the card with what works,
what is weak and numbered steps with clock times an editor can follow. The example's draft and its number are made up, but its new
opening was written, drawn and checked by the real pipeline. `--caso PATH` opens any other `resultado.json` inside the repo.

The panel is a "liquid glass" interface drawn with WebGL over backgrounds generated with
**Muse Image** (`panel/fondos/`); it falls back to plain CSS when WebGL is not available or the file is
opened with a double click. It only paints text from the JSON (never HTML) and only loads cases from
`casos/` on the same site.

## Try it with your own video

Works from a clean copy of this repository. You need Python 3.12, ffmpeg and your own key for the Meta Model API.

```bash
pip install -r requirements.txt
# ffmpeg:  winget install Gyan.FFmpeg  (Windows) · brew install ffmpeg (macOS) · apt install ffmpeg (Linux)
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env  (Retina reads .env at the repo root)
# Open .env and put your Meta Model API key in MODEL_API_KEY.
# Add BASETEN_API_KEY for Muse Spark Open; without it, Muse Spark 1.3 does its work.
PYTHONPATH=src python -m retina.app     # Windows PowerShell: $env:PYTHONPATH="src"; python -m retina.app
```

The app opens in your browser at `http://127.0.0.1:8790` (change it with `--puerto`). Drop a video in the page, write its
title and when it would go out, and the review is ready in about 3 minutes, in the language the page is in (English or
Spanish). Then press **Fix my opening**: you watch each step happen, and in about a minute you get the before and after.
It costs about USD 0.05 to 0.25 of your own credits, so it only runs when you press the button. The new opening comes out
in the language of the video.

Without the app, from the command line:

```bash
PYTHONPATH=src python -m retina.retina VIDEO --salida CARPETA --con-api --ya-publicado --idioma en
```


**Who it was tested on.** We tested Retina on horizontal videos of 1 to 4 minutes from one large Facebook page in
Spanish. It works for any creator and in English, but the new opening was measured on those videos.

Retina is built to review a video *before* you publish it, so by default any video goes to Meta's API, which
costs money (a review is about 10 US cents and fixing the opening 5 to 25 more; your own cap is in `.env`,
`RETINA_TOPE_USD`).
With the free credits of the contest, the content you send may be used by Meta; a company that does not
want to send drafts can turn on a lock with `RETINA_SOLO_PUBLICADOS=1` in its `.env`: then only
already-published videos go, and `--con-api` requires `--ya-publicado`.

No Badabun video or per-video data is needed. A company can add its own layer on top (its creators, its
history, its transcripts) with a private model. That layer is not part of this entry.

### Reproducing our measurements (needs the private data)

The measurements in `eval/` and the private model (`MODELO.pkl`) need Badabun's private
archive, which is not in this repository. `python -m retina.publico` rebuilds the public brain from such a
base. Without that data you can still read every rule in [`docs/decisiones.md`](docs/decisiones.md) and run
the tests.

### What else the app does

**From the browser.** Besides the video, the upload screen takes optionally who is on camera and a production
code (a date, code or name at the start of the file name, like `2026-01-15 XYZ0000001 Title.mp4`, is filled in;
useful only to a company with its own private model). The pipeline runs in the background, one video at a time, and the card
opens in the panel when it is ready (about 3 minutes). The app listens only on 127.0.0.1, accepts uploads only
from its own page and only video files: common video formats (MP4 and MOV are used as they are; WebM, MKV,
AVI and FLV are converted to MP4 with ffmpeg), and also an audio-only M4A. It honours the published-only lock
(`RETINA_SOLO_PUBLICADOS`) set in the `.env`.

**Compare two versions (A/B).** On the same upload screen, «Comparar dos versiones» takes two cuts of the
same video. Retina reviews each one and then `retina.comparar` asks Muse Spark Open (Muse Spark 1.3 as
rescue) which start is stronger and why, from what Retina saw in each start (segments, what is said,
silences, Meta's recommendations, each card). It judges in both orders and only declares a winner when both
orders agree; otherwise it says it is a tie. The panel shows the verdict, a side-by-side table and the
differences, and says plainly that the retention numbers barely move between two cuts of the same video
(they come from the kind of video, not from what is on screen). Output: `comparacion.json` in version B's
folder (`python -m retina.comparar CASE_A CASE_B` runs it by hand).

Every card, green ones included, now lists what works, what is weak and up to three optional improvements
(`lo_bueno`, `lo_flojo`, `mejoras_opcionales`), checked by the same validator as the main change.

The panel reads only `resultado.json`; its contract is in
[`docs/resultado-json.md`](docs/resultado-json.md), with a made-up example in
[`casos/demo/resultado.json`](casos/demo/resultado.json).

Requires Python 3.12 and ffmpeg (on PATH or in `FFMPEG`; on Windows, `winget install Gyan.FFmpeg`).
V-JEPA 2 and the local Whisper script are optional and need `pip install -r requirements-gpu.txt`
and a GPU; without them the pipeline still runs.

Tests (no API key, no private data): `pip install -r requirements.txt`, then
`python -m unittest discover -s tests`.

## Open weights: the agent runs on Muse Spark Open

The main step of Retina (in the company version an agent that investigates the opening; in the
public version a one-pass card) writes the card the editor sees on **Muse Spark Open** (`meta-models/muse-spark-open-1026`,
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

The public version (what you run from this repo) writes the card in one pass with the same
validator, because the agent's best tool looks up a company's own past videos. When Spark Open
cannot produce a card the validator accepts, Muse Spark 1.3 takes over, and the card says which
model wrote it. A blind judge preferred one-pass cards over the agent's (see Results).

## Results

**The opening fix.** The rule was sealed before each run. The first test failed: 10 of 18 openings with a visible promise passed,
because SAM did not know some words even when the drawing showed the object. We calibrated its vocabulary on made-up drawings
([`eval/calibrar_vocabulario.py`](eval/calibrar_vocabulario.py)): of 167 words, 104 work as they are, 10 work through a general word
("tortilla" is searched as "food") and 53 can no longer be checked with SAM. Then we sealed a new rule and ran it on 30 videos never
used for this: **29 of 30 passed every check** (95 % interval, 83 % to 99 %), 23 on the first try and 6 after one correction. SAM
rejected 9 of 10 trap frames, the minimum; the tenth asked for a building in a drawing that does show buildings. It cost USD 1.84.

What this does not show: about a third of titles (30 of 83) promise something SAM can check, and the rest get only the text and
frame rules. That test used the title and the speech, without the video. And it measures passing the checks, not keeping people.

The rest of this section is what we measured on the way there, while Retina still had a number. It is why Retina now
promises only what it can check. What was measured where. Every measurement is on videos the model had not seen, but the periods and the
comparison rule differ, so do not read the rows as one test:

- **Predicted curve, opening level and reach** (house model): Jul–Sep 2026, against today's rule, "the average
  of videos of the same talent and duration over the previous 90 days".
- **Creators it has never seen, the public brain, the opening sheet and the traffic light**: Jul–Dec 2025 and
  Jan–Jun 2026 (the creator-never-seen test also used Jul–Sep 2026), against a fixed curve by duration, the
  one the public mode uses. Several of these periods were used more than once, and we say so where it matters.
- **The agent and the card comparisons**: the same 50 videos (Jul–Sep 2026), which we also used to tune the
  agent's instructions.

No number is reported before it is measured, and figures from Badabun's private data are not published.

| Question | What we found |
|---|---|
| Does the predicted curve beat today's rule? | Yes, on all five measures (error at 3 s, 15 s, mid-video, end, whole curve), in Jul–Sep 2026. The figures stay private. |
| When Retina says the opening risk is "high", does the opening really lose more people? | Clearly more often than the base rate, measured against similar videos *of the same production type* so the type alone can't explain it. We did not show that the gap holds inside each type: we only compared one production type against the rest, and inside that type the ranges touch. The figures stay private. |
| Can it point to the exact stretch where people leave? | No. Past the opening it does worse than always guessing the most common stretch, because the curve comes in whole points. We dropped that promise. |
| Does speech help the risk level? | No, measured twice. Speech goes to the agent's explanation instead. |
| Does it work for a creator it has never seen? | Better than before, not as well as for a creator it knows. We hid whole groups of creators from training and history, then fed in their videos the way an outside video arrives: no creator, no production code, only the published title. A brain built only from what any video has (length, vertical or not, posting time, title, and how the speech opens) was compared with the metadata model on those same videos. The rule was written before measuring, and **the first period (Jul–Sep 2026) did not pass it**. We then changed the comparison (a paired difference per video) after seeing that result, so that period counts as a hint. The new rule was written before running on a second period (Jan–Jun 2026), and it passed: a small, real improvement ([`eval/cualquier_video.py`](eval/cualquier_video.py), [`docs/decisiones.md`](docs/decisiones.md), which admits the change). Retina uses it for creators it doesn't know and says so on the card; videos from the house keep the model that knows them. The public brain file (trained without paid, out-of-scope or serious-topic videos and without creator names) passed its own rule against the fixed curve by duration in Jan–Jun 2026. Against the plain average for its duration, it **loses in Jul–Dec 2025** and only ties in Jan–Jun 2026. The figures stay private. |
| Does reading the opening make the number better? | Yes. Muse Spark Open labeled the opening of every video since 2022 (hook tactic, clarity, curiosity...). With that sheet, the public brain missed by less for creators it never saw and ordered videos better, on two held-out periods, with the rule sealed by a commit before measuring ([`eval/cualquier_video.py`](eval/cualquier_video.py), variant E). One caveat: the sheets we measured were written without a fixed temperature and 20 videos per call; the app asks for one video at a time at temperature 0, so the sheet that runs in the app is not identical to the one we measured, and we have not measured that difference. The figures stay private. |
| Does the traffic light work? | Not well enough to show it in the public mode. We wrote the rule before measuring and sealed it with a commit. The test did not hide any creator from the model. On two held-out periods, videos flagged "high" lost more people than the base rate and "low" ones less, but in one period it flagged too many videos as "high", above the limit we had set. By our own rule the first version does not pass. A second version passed its own rule, but we wrote it after seeing the first one fail, and it was tested on periods already used several times, so we treat it as exploratory and it is **not** in the public mode: the card says what it saw and the number stays as a reference ([`eval/semaforo_publico.py`](eval/semaforo_publico.py), [`eval/semaforo_publico_v2.py`](eval/semaforo_publico_v2.py)). The figures stay private. |
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

- Before the event we explored the data in private notes (with the same test cut-off and the rule of
  the previous 90 days). The code in this repository is new, and every figure was redone during the event.

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
