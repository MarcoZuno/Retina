# What we measured

Every question below that says "rule written first" had its pass/fail rule in [`decisiones.md`](decisiones.md) before the run. From
29-Oct on, those rules were also sealed with a git commit before measuring. We report what failed as well as what passed. The numbers
come from a private Facebook archive of one large page in Mexico, in Spanish and mostly horizontal; they stay out of this repository
unless a figure is given here.

[`decisions-summary.md`](decisions-summary.md) tells the same story in order, in English.

## The opening fix

| Question | Rule written first | Result |
|---|---|---|
| Third test: does the opening pass every check with the final instructions and with nothing ordered to the drawing? | See below | **PENDIENTE_TERCERA** |
| First test, 50 videos: can Retina rewrite an opening that keeps the title's promise and breaks no rule? | At least 15 of 18 openings with a visible promise pass every check in 2 corrections or fewer, 26 of the other 32 pass, SAM rejects 9 of 10 trap frames | **Did not pass.** 10 of 18. The other two parts passed (31 of 32, and 10 of 10). SAM did not know words like "tortilla" even when the drawing showed one |
| Second test, 30 other videos, after calibrating SAM's vocabulary | At least 24 of 30 pass everything, SAM rejects 9 of 10 trap frames | **Passed, but read it as a regression test, not a validation.** 29 of 30, 23 on the first try, 9 of 10 traps |

**Why the second test is only a regression test.** It shows the fix for the first failure worked, not that the method holds up.
We removed the words SAM could not find (53 of 167 can no longer be checked with SAM). The code told Muse Image to draw the promised
object "large and centered", and that same object is what SAM then looked for. Five of the eight failures of the first test could no
longer happen. A reviewer estimated that passing was the likely result, about 96 times in 100. Ten of the 30 cases were a dog or an
animal, across 23 distinct words, so the 95 % interval of 83 % to 99 % treats as independent cases that are not. It used title and
speech, without the video, and had no group without a visible promise.

Three of the first test's traps used words SAM barely recognizes (nopal, fair, handkerchief), so that "10 of 10" tells us about 7 of 7.
The traps also skipped objects of the same family, which is where the check is weak: "hospital" and "school" are searched as
"building", so any building passes.

**What the third test changed.** The code no longer orders the drawing: the writer receives the promised object and the frame is drawn
only from what the writer wrote, so SAM checks the writing. The instructions no longer say "bring the promise to the start"; they say
to give the first proof and leave the rest to the video, because the old rule emptied the video (one example gave away the three
tricks in 14 of 96 seconds). The test adds a group without a visible promise, traps from the same family, and a blind judge.

PENDIENTE_DETALLE

## The reference number

Method, data, fitting details and the margin are in [`numero.md`](numero.md).

| Question | Rule written first | Result |
|---|---|---|
| Can the predicted curve beat today's rule (the average of videos of the same duration and creator over the previous 90 days)? | Beat it on error at 3 s, 15 s, mid-video, end and whole curve | **Passed**, house model, Jul-Sep 2026 |
| Does Retina work for a creator it has never seen? | Lower error on the whole curve and better ordering at 15 s, with intervals that do not overlap | **First period did not pass.** We then changed the comparison (a paired difference per video), which makes that period a hint, not a result. A second period, with the new rule written before running, **passed**: a small, real improvement |
| Does the public brain file (no video, no creator names) hold up? | Beat the fixed curve by duration on a period it had not seen | **Passed** on Jan-Jun 2026. Against a fresh 90-day average for its duration it lost in Jul-Dec 2025 and tied in Jan-Jun 2026 |
| Does reading the opening (a fixed sheet filled by Muse Spark Open) improve the number? | Better in both of two periods | **Passed**, by 1.4 to 2 people per 1,000 over the whole curve, with the rule sealed before measuring. One caveat: those sheets were written without a fixed temperature and 20 videos per call; the app asks for one video at temperature 0, and we have not measured that difference |
| How far off is the number? | No pass/fail rule: this sets the margin the panel shows | Off by 8.9 people of 100 on hidden creators, and 10.2 on hidden creators after the training period, against 10.4 and 11.7 for the fixed curve alone. The panel says give or take 11 |
| Can the number compare two versions of one video? | Exploratory, no rule | **No.** On 41 rewritten openings it fell in 27, rose in 7 and barely moved in 7. It learned from differences between videos, so Retina shows no number for the new opening. This does not show the new opening is worse: no real retention was involved |
| Does a better opening go with more reach on Facebook? | A positive relation, in two separate periods and then on a later period with the prediction made as if before publishing | **Passed**, as a relation, not proof of cause. With real retention, the best third reached about 3.5 times more people than the worst third. With the prediction it was about 1.5 times (95 % interval 1.2 to 2.0), using the house model. The public brain was never measured for this. The third check was a backtest run on 29-Oct, not a prediction logged before publishing |

## The opening level

| Question | Rule written first | Result |
|---|---|---|
| Does the "high / medium / low" opening level pick out openings that really lose more people? | Better than the base rate, against videos of the same production type | **Passed**: openings flagged "high" lost more people than the base rate. We did not show that the gap holds inside each type |
| Does the traffic light work for creators it has never seen (v1)? | "High" for 15-35 % of videos, clearly above the base rate, "low" below it, in two periods | **Did not pass**: it flagged too many videos as "high" in one period. **The public mode shows no traffic light** |
| A second traffic light (v2)? | Same rule as v1 | It passed, but it was written after seeing v1 fail and tested on periods already used several times. By our own rule it counts as exploratory and **is not in the public mode** |
| Can we point to the exact stretch where people leave? | Beat always guessing the most common stretch | **Did not pass.** The curve comes in whole points, so past the opening it is rounding noise. We dropped the promise |
| Does speech improve the risk level? | Improve it on held-out videos | **Did not pass**, measured twice. Speech goes to the explanation instead |
| Does looking at the video (frame features, audio, pace) improve the risk level? | Improvement above zero, with a confirmation period set in advance | **Did not pass** in either period |
| Can Spark, watching two openings, say which loses more people? | Better than a coin flip, each pair judged in both orders | **Did not pass.** It was no better than a coin flip and the data model beat it |

## The card and the agent

| Question | Rule written first | Result |
|---|---|---|
| Do the agent's tools make the card better than one pass? | The agent wins at least 60 % of firm pairs in a blind comparison | **Did not pass.** The blind judge preferred the one-pass card in 27 of 39 firm pairs, so the public version writes the card in one pass. The judge only sees the data the one-pass card had, so what the agent found with its tools can look invented to it |

Measured on the same 50 videos as the Spark 1.3 agent ([`eval/casos_agente.py`](../eval/casos_agente.py)). They were published from July
to September 2026, after the models' training cut, but we also used them to tune the agent's instructions, so read this as a
comparison between the two models, not as a clean test. One run each.

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

Spark Open writes longer texts and reaches for phrases our rules block more often, so the validator sends its first card back more
often (mostly a text over 220 characters or an engagement-bait phrase). It fixes them inside the loop. Written in one shot, without
tools, Spark Open is clearly weaker than Spark 1.3 (28 of 50 cards passed the validator on the first try, against 46;
[`eval/casos_spark_open.py`](../eval/casos_spark_open.py)), and raising its reasoning effort did not help there (22 of 50). What closed
the gap was letting it work as an agent.

## Not measured

- **Facebook's rules check.** It has no rule and no measurement. It reads what Muse Spark 1.3 wrote about what is on screen and what
  Muse Voice Transcribe heard, not the video file itself. Code drops any warning whose quote is not in that second of the video.
- **Whether the new opening keeps more people watching.** Never measured, and Retina does not promise it.
- **Any audience or human judgment of the new openings.** The blind judge is a model.
- **Retina outside its data.** Everything was measured on one large page, in Spanish, mostly horizontal. It runs on other creators
  and in English; we only checked that it runs.
- **Comparing two cuts.** The A/B screen asks Spark which start is stronger from what Retina saw. That is an opinion about the two
  starts, not a retention result: when we tested Spark on telling which of two openings loses more people, it did no better than a coin flip.

## Which period is which

Every measurement is on videos the model had not seen, but the periods and the comparison rule differ, so do not read the rows as one test.

- **Predicted curve, opening level and reach** (house model): Jul-Sep 2026, against the average of videos of the same talent and duration
  over the previous 90 days.
- **Creators it has never seen, the public brain, the opening sheet and the traffic light**: Jul-Dec 2025 and Jan-Jun 2026 (the
  creator-never-seen test also used Jul-Sep 2026), against a fixed curve by duration, the one the public mode uses. Several of these
  periods were used more than once, and we say so where it matters.
- **The agent and the card comparisons**: the same 50 videos (Jul-Sep 2026), which we also used to tune the agent's instructions.

Creator labels exist only from 2024 on, so "creators it has never seen" is weaker for older videos, and a variant of a creator's name can
still show up in another group's titles.
