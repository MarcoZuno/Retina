# The live run in the video

The 3-minute video shows one run of `python -m retina.app` with a Meta Model API key and a Baseten key, on a 76-second
vertical reel in Spanish, recorded on 3-Nov-2026 in one take. A private script drove the browser the way a person would:
it clicked, typed and scrolled, and the panel was not modified. For the video, the two waits were sped up 4× and are labeled
on screen; everything else runs at real speed. The reel, its title and its transcript belong to the creator and are not in
this repository.

What the panel showed, second by second, and which model was working:

| Second | What the panel showed | Model |
|---|---|---|
| 0:23 | Review requested | |
| 0:23 to 2:52 | Review in progress: cut, transcribe, opening sheet, number, describe, SAM, card, rules, title | Muse Voice Transcribe 1.0, Muse Spark Open, Muse Spark 1.3, SAM 3.1 |
| 2:52 | Review card on screen | |
| 3:54 | "Fix the opening" pressed | |
| 3:58 | "Muse Spark Open is writing your opening…" | Muse Spark Open |
| 4:11 | "Something didn't pass the checks. Muse Spark Open is fixing it…" Attempt 1 listed several things instead of giving one proof; a code rule rejected it | Muse Spark Open |
| 4:26 | "Muse Spark 1.3 is reading the opening against what your video says…" | Muse Spark 1.3 |
| 4:30 | "Muse Image is drawing the first frame…" | Muse Image 1.0 |
| 4:47 | "SAM 3.1 is looking for what the title promises…" | SAM 3.1 |
| 5:32 | "Everything passed. Muse Image is drawing the other two frames…" | Muse Image 1.0 |
| 6:05 | "Muse Spark 1.3 checks each drawing shows what it says…" | Muse Spark 1.3 |
| 6:12 | New opening on screen: "Retina rejected it once and fixed it" | |

The review took 2 minutes 29 seconds and the opening 2 minutes 18 seconds, with the API's own latency on that day.

## Two runs that failed the same day

Two earlier runs that day, on the same reel, ended with "We couldn't get an opening to pass every check": attempt 1 listed
several things, attempt 2 added a detail the video does not say (Muse Spark 1.3 caught it), attempt 3 listed several things
again. The day before, one run had passed on the first try. The model is not deterministic, and a run that fails shows no
opening at all, by design. We say this here because a judge who runs Retina on a video of their own may see it.
