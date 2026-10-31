# Retina

**Retina rewrites the first seconds of your video, draws them and checks the fix before you publish. Then it tells you how many people may stay, with its margin of error.**

![Retina's before and after for a made-up example video: the draft opens with a greeting and no bread in sight; the new opening shows the bread from the first frame, with the list of checks it passed](docs/img/retina-example-card.jpg)

*Made-up example, with drawings by Muse Image. Open it yourself in one minute, with no key: see below.*

Most tools read a video and hand you a grade. Retina hands you a new first 10 to 15 seconds that you can watch and hear. Its core is a
rule engine and a verification loop around Meta's models: the rules run in code, after the model, and send the work back with the exact
list of what failed. One prompt to one model cannot do this.

1. **Watch and listen.** Muse Spark 1.3 describes what is on screen and Muse Voice Transcribe writes down what is said.
2. **Rewrite.** **Muse Spark Open**, Meta's open-weight model, writes a new opening that gives the first proof of what the title
   promises and leaves the rest to the video. The title itself is never touched.
3. **Check the words.** Fixed code rules read the result: none of the engagement bait Meta's distribution rules penalize, nothing that
   touches logos, legal notices or credits, the title's topic in the first sentence, and a length that fits 10 to 15 seconds. Numbers
   and mid-sentence names must come from the video.
4. **Draw it.** **Muse Image** draws the first frame from what Spark Open wrote.
5. **Check the picture.** **SAM 3.1** looks in that frame for what the title promises, picked by Muse Spark 1.3 from a closed list of
   objects and places, never people.
6. **Correct.** If anything fails, Spark Open receives the exact list of failures and tries again, up to twice. What does not pass
   never reaches you.

**How many people may stay.** Retina also estimates how many of every 100 people who get past the first 3 seconds will still be watching
at 15 seconds, give or take 11. It learned this from 23,710 videos of a large Facebook page in Mexico. It is a modest reference, not a
promise: in about 9 of 10 videos the difference from similar videos is smaller than the margin, and Retina says so instead of inventing one.

It also checks what is seen and said in the video against 18 of Facebook's public rules, with the second and the words behind each warning.

## What we measured

Pass/fail rules were written before each run. The full list, including everything that failed, is in [`docs/results.md`](docs/results.md).

| Question | Result |
|---|---|
| Does a new opening pass every check, with nothing ordered to the drawing? (third test, 50 new videos) | **Passed**: 29 of 30 with a visible promise and 17 of 20 without one, in 2 corrections or fewer. The 4 that failed were withheld, as designed |
| Can the picture check be fooled? | SAM rejected 10 of 10 frames asked for an object of another family, and 10 of 10 asked for a close one, like a cat in a dog's frame |
| Is the new opening faithful, and does it leave something for the rest of the video? | A blind judge said yes to both in 45 of 46. The judge is a model, not people |
| Is it clearer than the video's real opening? | The same judge preferred the new one in 37 of 42 firm pairs. It compares clean writing with raw speech, which favors the new one |
| Earlier tests | The first failed (10 of 18). The second passed (29 of 30), but it was a regression test, not a validation |
| How far off is the number? | Give or take 11 people out of 100, on creators and dates it had not seen. It beats the fixed curve by little |
| Does the new opening keep more people? | **Not measured** |

## Limits we say out loud

- **Retina does not know whether the new opening keeps more people.** We never measured that, and it shows no number for the new opening.
- **The tests used the title and the speech, not the video,** on one page's archive. Fourteen of the 30 cases with a promise were pets or
  animals, so the intervals in the annex count as independent cases that are not.
- **The "after" is a sketch,** drawings and voice, not a filmed video.
- **The number cannot see the first 3 seconds.** Facebook's curve seems to count only people who got that far.
- **Checking is not truth.** Retina checks that numbers and names come from your video, not that they are true. A name at the very start
  of a sentence, or a quantity like "half a ton", can slip past the rules. Ten words are checked through a general one, so "hospital"
  passes with any building.
- **The rules check is a first look,** not a guarantee, and we have not measured it. Meta makes the final call.
- **Measured on one page.** Everything was measured on one large page, in Spanish, mostly horizontal, 1 to 4 minutes. It runs on other
  creators and in English, but we only checked that it runs.
- **Spanish and English only.** The new opening comes out in one of those two. A video in another alphabet is declined before spending.

## Try it in one minute (no key, no GPU)

```bash
PYTHONPATH=src python -m retina.demo      # Windows PowerShell: $env:PYTHONPATH="src"; python -m retina.demo
```

You only need Python. It opens a made-up example in your browser, served only on your machine: the opening before and after, every check it
passed, the number and the check against Facebook's rules. The example's draft and number are made up; its new opening was written, drawn
and checked by the real pipeline.

## Try it with your own video

You need Python 3.12, ffmpeg and your own key for the Meta Model API.

```bash
pip install -r requirements.txt
# ffmpeg:  winget install Gyan.FFmpeg  (Windows) · brew install ffmpeg (macOS) · apt install ffmpeg (Linux)
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
# Put your Meta Model API key in MODEL_API_KEY. Add BASETEN_API_KEY for Muse Spark Open; without it, Muse Spark 1.3 does its work.
PYTHONPATH=src python -m retina.app     # Windows PowerShell: $env:PYTHONPATH="src"; python -m retina.app
```

The app opens at `http://127.0.0.1:8790`. Drop a video, write its title, and the review is ready in about 3 minutes (about USD 0.10). Then
press **Fix my opening**: you watch each step happen, and in about a minute you get the before and after (USD 0.05 to 0.25, only when you
press the button). Your spending cap is `RETINA_TOPE_USD` in `.env`. With the contest's free credits, Meta may use what you send; a
company that does not want to send drafts can set `RETINA_SOLO_PUBLICADOS=1`.

From the command line:

```bash
PYTHONPATH=src python -m retina.retina VIDEO --salida FOLDER --titulo "Your title" --con-api --ya-publicado --idioma en
```

Tests need no key and no private data: `pip install -r requirements.txt`, then `python -m unittest discover -s tests`.

## Meta models in Retina

| Step | Model | Where it runs | What it does |
|---|---|---|---|
| Rewriting the opening (main step) | **Muse Spark Open** (open weights) | Baseten Model API | Writes the new opening and three frames, and fixes them when a check fails. Without a Baseten key, Muse Spark 1.3 does it |
| Drawing it | **Muse Image 1.0** | Meta Model API | Draws the first frame and, once everything passes, the other two |
| Checking the promise | Muse Spark 1.3 + **SAM 3.1** | Meta Model API | Spark picks what the title promises from a closed list; SAM looks for it in the first 3 s of the draft and in the first drawn frame |
| Checking Facebook's rules | Muse Spark 1.3 | Meta Model API | Reads the description and transcript against a closed list of 18 public rules; code drops any warning without real evidence |
| Watching and listening | Muse Spark 1.3, Muse Voice Transcribe 1.0 | Meta Model API | What is on screen, speech with timestamps and silences |
| Reading the opening, writing the card | **Muse Spark Open** (open weights) | Baseten Model API | Fills a fixed sheet about how the opening starts; writes what works and what is weak, checked by a validator. Muse Spark 1.3 rescues |

### What is not a Meta model

- **The reference number** is a ridge regression fitted offline on Badabun's retention data: at runtime, a JSON file of fixed weights
  that plain Python multiplies and adds. It adjusts the average curve for the video's length, writes nothing and decides nothing. Ridge in
  closed form, λ = 300, 1,703 inputs to the 41 points of the curve, on 23,710 of 32,906 videos: left out are the rest for eligibility or topic; 9,003 of those used have no opening sheet and 974 no speech. The weights are in
  [`modelos/retina-publico.json`](modelos/retina-publico.json) and the method in [`docs/numero.md`](docs/numero.md). The organizers ruled on
  30-Oct-2026 that ridge coefficients are acceptable when explained this way. `RETINA_SOLO_MODELOS_META=1` turns it off.
- **The voice in the preview** is your browser's own speech synthesis, which may be a neural voice from your system or browser. Retina
  does not call it through an API, and it is not a Meta model.
- **Whisper** ran offline, once, to transcribe the archive for training. It never runs in the app.
- **ffmpeg** cuts the video. **V-JEPA 2** (Meta's open weights) was research only and is not needed.

## What existed before, and what we built

Before 26-Oct-2026 Badabun already had the private list of published videos with their 41-point Facebook retention curves, its Graph API
reader and its servers. They stay private. Everything in this repository was written during the event, from 26-Oct-2026 on, and every
figure here was redone during the event. The day-by-day diary is in [`BUILD-LOG.md`](BUILD-LOG.md), in Spanish, with an English summary in
[`docs/decisions-summary.md`](docs/decisions-summary.md).

More: [`docs/architecture.md`](docs/architecture.md) for the services, the agent and the app.

## Team

Built by Badabun (Mexico) for the Meta Global AI Developer Hackathon 2026 · Startup track · theme *Build for Your World*.

**Marco Zuno** (representative) · **Jossafat Ruvalcaba** (lead developer). The code was written with Claude Code, which the organizers
allow, directed by Jossafat. Commits go through the representative's account, which owns this repository, so they show Marco Zuno and Claude.

## License

[MIT](LICENSE).
