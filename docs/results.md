# What we measured

Every question below that says "rule written first" had its pass/fail rule in [`decisiones.md`](decisiones.md) before the run. From
29-Oct on, those rules were also sealed with a git commit before measuring (see "About the seals" below). We report what failed as well as what passed. The numbers
come from a private Facebook archive of one large page in Mexico, in Spanish and mostly horizontal; they stay out of this repository
unless a figure is given here.

[`decisions-summary.md`](decisions-summary.md) tells the same story in order, in English.

## The fifth test, the version published here

A review of the fourth test's version, read as a jury would, found four things that changed the product. Retina was rewriting out-of-scope topics and
health advice, and nothing filtered them: 25 of that test's 50 videos would no longer be rewritten. Nothing in the product stopped an
unfaithful opening; the judge existed only in the tests, and 3 of 47 would have reached the person. Greetings passed, and so did openings
of 18 words, which is about 6 seconds. So the fourth test no longer described what we publish, and the version changed (`apertura-v4`).
Muse Spark 1.3 now declines out-of-scope topics and health advice before spending, and reads each opening against what the video says before it is
drawn. A code rule rejects greetings and the minimum rose to 25 words. The rule and the list of videos were sealed before running, with the
same nine conditions and the same numbers as the fourth test.

| Fifth test | Rule | Result |
|---|---|---|
| A. With a visible promise | At least 24 of 30 pass everything in 2 corrections or fewer, or the opening is confirmed as already good | **25 of 30** (95 % interval 66 % to 93 %) |
| B. Without a visible promise | At least 16 of 20 pass the same, without SAM | **18 of 20** (70 % to 97 %) |
| C. Far trap | SAM rejects at least 9 of 10 approved frames asked for an object of another family | **10 of 10** |
| D. Judge: faithful, reading everything the video says | At least 80 % of approved openings | **42 of 43** (88 % to 100 %) |
| E. Judge: leaves something important for the rest of the video | At least 80 % of approved openings | **42 of 43** (88 % to 100 %) |
| F. Judge against the real first 15 seconds, labels hidden, in both orders | The new one wins at least 60 % of firm pairs, with at least 20 decided | **35 of 37 firm pairs** (95 %); 2 for the real opening, 6 changed with the order |
| G. Negative control: 10 openings with an invented fact planted | The judge rejects at least 9 as not faithful | **10 of 10** |
| H. Negative control: 10 summaries of the whole video used as the opening | The judge says at least 7 leave nothing | **8 of 10** |
| I. Spark Open does not take the easy way out | At most 10 of 50 openings are declared already good | **0 of 50** |

Reported, not conditions:

- **What Retina left alone.** Picking these 50 meant reviewing 234 titles and speech; 125 were out as out-of-scope topics or health advice. Every figure
  above describes the rest.
- **Near trap: 8 of 10 rejected.** "Store" passed on a shop and "dog" passed on a frame asked for an animal, both close to the same thing.
  The pairs change between tests, so read this with the fourth test's 7 of 10.
- **Corrections.** Of the 43 approved, 27 passed on the first try, 12 after one correction and 4 after two. What got corrected: more than one
  proof given at once (13), something the video does not say (8), the promise (7), a name (3), engagement bait (2), frames (2).
- **The 7 that failed were withheld:** four where the read-back kept finding something the video does not say, and one each for the promise, the
  frames and more than one proof.
- **The read-back in the product.** It sent back 11 of the 50 openings at least once. Nothing was left unchecked: no check failed to run.
- **Frames.** All 104 frames that SAM did not check matched what was written, in the approved openings. No frame was left unchecked.
- **Cost.** USD 4.82 for the rewriting, or about USD 0.10 per video, plus the judge.

How to read it:

- **A passed by one case:** 25 against a minimum of 24. The condition was met, and that is all it shows.
- **Do not read D to H as people's opinion.** The judge is Muse Spark 1.3, a model. No person and no audience judged these openings.
- **D is no longer independent of the loop.** The judge is the same model that reads the opening inside Retina, with almost the same
  questions, so a high D says less than it did in earlier tests.
- **The judge is blind only in F.** In D and E it knows it is reading the new opening.
- **41 of 43 passed D and E together.** One opening was faithful but left nothing, and one left something but was not faithful.
- **F favors the new opening.** It compares clean writing with raw transcribed speech.
- **G and H are planted, obvious failures.** They show the judge can say no, not that it catches every subtle one.
- **"Already good" was not exercised.** It came up 0 times in 50 here and 0 times in the 6 tuning cases, so condition I says nothing about
  how good that verdict is.
- **There was no video.** This test used the title and the speech.
- **The cases are not independent.** 13 of the 30 with a promise are animals, and 21 distinct objects cover the 30.
- The instructions were tuned on 6 separate cases, run once and left unchanged, which are not part of this test.
- **Whether the new opening keeps more people was not measured.**

**About the seals.** A seal is a git commit in this repository's own history, made before the run, and that history was recreated for
publication ([`hash-map.md`](hash-map.md) gives the new hashes). Nothing outside the repository timestamps it. The list of videos is
private, so you can check its fingerprint in [`decisiones.md`](decisiones.md) only against that list. The rule, the conditions and the
results are public. The code that ran the fifth test, the instructions and the rules are the same ones published here.

## Earlier tests of the opening fix

### The fourth test, the version before this one (`apertura-v3`)

The third test showed the openings pass. A review of its results then found two real ones that were worse than the original: they listed
every sign the video was about to explain and erased the speaker's authority. Frames 2 and 3 were never checked, and the judge had never
seen a bad opening planted on purpose. So the instructions changed (`apertura-v3`), a code rule now rejects lists, Muse Spark 1.3 checks
the frames SAM does not, and the judge got a negative control. The rule and the list of videos were sealed before running. It no longer describes what we publish: see the fifth test.

| Fourth test | Rule | Result |
|---|---|---|
| A. With a visible promise | At least 24 of 30 pass everything in 2 corrections or fewer, or the opening is confirmed as already good | **27 of 30** (95 % interval 74 % to 97 %) |
| B. Without a visible promise | At least 16 of 20 pass the same, without SAM | **20 of 20** (84 % to 100 %) |
| C. Far trap | SAM rejects at least 9 of 10 approved frames asked for an object of another family | **10 of 10** |
| D. Judge: faithful, reading everything the video says | At least 80 % of approved openings | **44 of 47** (83 % to 98 %) |
| E. Judge: leaves something important for the rest of the video | At least 80 % of approved openings | **46 of 47** (89 % to 100 %) |
| F. Judge against the real first 15 seconds, labels hidden, in both orders | The new one wins at least 60 % of firm pairs, with at least 20 decided | **36 of 41 firm pairs** (88 %); 5 for the real opening, 6 changed with the order |
| G. Negative control: 10 openings with an invented fact planted | The judge rejects at least 9 as not faithful | **10 of 10** |
| H. Negative control: 10 summaries of the whole video used as the opening | The judge says at least 7 leave nothing | **9 of 10** |
| I. Spark Open does not take the easy way out | At most 10 of 50 openings are declared already good | **0 of 50** |

Reported, not conditions:

- **Near trap: 7 of 10 rejected.** "School" passed on a drawn house twice, because both are searched as "building", and "medicine" passed
  on a pill. The third test's 10 of 10 used other pairs.
- **Corrections.** Of the 47 approved, 37 passed on the first try, 8 after one correction and 2 after two. What got corrected: the promise
  (5), more than one proof given at once (5), engagement bait (3), frames (2), a number, a name and the topic (1 each).
- **The 3 that failed were withheld:** two where SAM did not find the promise and one with a name the rules rejected.
- **Frames.** All 114 frames that SAM did not check matched what was written, in the approved openings. No frame was left unchecked.
- **Cost.** USD 4.12 for the rewriting, or USD 0.08 per video, plus the judge.

How to read it:

- **Do not read D to H as people's opinion.** The judge is Muse Spark 1.3, a model. No person and no audience judged these openings.
- **The judge is blind only in F.** In D and E it knows it is reading the new opening.
- **43 of 47 passed D and E together.** One opening was faithful but left nothing; three left something but were not faithful.
- **F favors the new opening.** It compares clean writing with raw transcribed speech.
- **G and H are planted, obvious failures.** They show the judge can say no, not that it catches every subtle one.
- **"Already good" was not exercised.** It came up 0 times in 50 here and once in the 6 tuning cases, so condition I says nothing about
  how good that verdict is.
- **There was no video.** This test used the title and the speech.
- **The cases are not independent.** 8 of the 30 with a promise are pets or animals, and 20 distinct objects cover the 30.
- The instructions were tuned on 6 separate cases, run twice, which are not part of this test.
- **Whether the new opening keeps more people was not measured.**

| Question | Rule written first | Result |
|---|---|---|
| Third test, 50 new videos, with the previous instructions (`apertura-v2`): does the opening pass every check once the code stops ordering the drawing? | At least 24 of 30 with a visible promise, 16 of 20 without one, SAM rejects 9 of 10 far traps, and the judge's three conditions below | **Passed all six**, on the first run. 29 of 30 and 17 of 20 |
| First test, 50 videos: can Retina rewrite an opening that keeps the title's promise and breaks no rule? | At least 15 of 18 openings with a visible promise pass every check in 2 corrections or fewer, 26 of the other 32 pass, SAM rejects 9 of 10 trap frames | **Did not pass.** 10 of 18. The other two parts passed (31 of 32, and 10 of 10). SAM did not know words like "tortilla" even when the drawing showed one |
| Second test, 30 other videos, after calibrating SAM's vocabulary | At least 24 of 30 pass everything, SAM rejects 9 of 10 trap frames | **Passed, but read it as a regression test, not a validation.** 29 of 30, 23 on the first try, 9 of 10 traps |

**Why the second test is only a regression test.** It shows the fix for the first failure worked, not that the method holds up.
We removed the words SAM could not find (53 of 167 can no longer be checked with SAM). The code told Muse Image to draw the promised
object "large and centered", and that same object is what SAM then looked for. Five of the eight failures of the first test could no
longer happen. A later review estimated that passing was the likely result, about 96 times in 100. Ten of the 30 cases were a dog or an
animal, across 23 distinct words, so the 95 % interval of 83 % to 99 % treats as independent cases that are not. It used title and
speech, without the video, and had no group without a visible promise.

Three of the first test's traps used words SAM barely recognizes (nopal, fair, handkerchief), so that "10 of 10" tells us about 7 of 7.
The traps also skipped objects of the same family, which is where the check is weak: "hospital" and "school" are searched as
"building", so any building passes.

**What the third test changed.** The code no longer orders the drawing. The order moved to the writer: it receives the promised object and
must describe it, and the frame is drawn only from what it wrote. So SAM confirms that the writer and the drawing obeyed, not that the
claim is true or that the video shows it. The instructions no longer say "bring the promise to the start"; they say
to give the first proof and leave the rest to the video, because the old rule emptied the video (one example gave away the three
tricks in 14 of 96 seconds). The test adds a group without a visible promise, traps from the same family, and a model judge, blind only in the comparison.

| Third test | Rule | Result |
|---|---|---|
| A. With a visible promise | At least 24 of 30 pass everything in 2 corrections or fewer | **29 of 30** (95 % interval 83 % to 99 %) |
| B. Without a visible promise | At least 16 of 20 pass everything but SAM | **17 of 20** (64 % to 95 %) |
| C. Far trap | SAM rejects at least 9 of 10 frames asked for an object of another family | **10 of 10** |
| D. Judge: faithful | At least 80 % of approved openings | **45 of 46** |
| E. Judge: leaves something important for the rest of the video | At least 80 % of approved openings | **45 of 46** (44 of 46 passed D and E together) |
| F. Judge against the real first 15 seconds, labels hidden, in both orders | The new one wins at least 60 % of firm pairs, with at least 20 decided | **37 of 42 firm pairs** (88 %); 5 for the real opening, 4 changed with the order |

Reported, not conditions: 10 of 10 near traps rejected, such as a cat asked of a dog's frame. Of the 46 approved, 41 passed on the first try, 3
after one correction and 2 after two. The 4 that failed were withheld: one where SAM never found the promise, one where the frames could
not be drawn, one with a name the rules rejected and one with engagement bait. The rewriting cost USD 3.00. As a reference, the same
judge on the 29 openings of the previous version found 29 faithful, and 26 that leave something for the rest.

How to read it:

- **Do not read D, E and F as people's opinion.** The judge is Muse Spark 1.3, a model. No person and no audience judged these openings.
- **F favors the new opening.** It compares clean writing with raw transcribed speech, including greetings and false starts.
- **The fix to the emptied video is a hint, not a result.** 45 of 46 against 26 of 29 are different videos and the intervals overlap.
- **The cases are not independent.** Fifteen of the 30 with a promise are pets or animals.
- **The near trap does not cover general words.** "Hospital" and "school" are still searched as "building".
- **There was no video.** Like the second test, this one used the title and the speech. The first test is the one that used the video.
- The instructions were tuned on 6 separate cases, run twice, which are not part of this test. The rule, the commit (c439813 in the
  original history) and the fingerprints are in [`decisiones.md`](decisiones.md).

## The reference number

Method, data, fitting details and the margin are in [`numero.md`](numero.md).

| Question | Rule written first | Result |
|---|---|---|
| Can the predicted curve beat today's rule (the average of videos of the same duration and creator over the previous 90 days)? | Beat it on error at 3 s, 15 s, mid-video, end and whole curve | **Passed**, house model, Jul-Sep 2026 |
| Does Retina work for a creator it has never seen? | Lower error on the whole curve and better ordering at 15 s, with intervals that do not overlap | **First period did not pass.** We then changed the comparison (a paired difference per video), which makes that period a hint, not a result. A second period, with the new rule written before running, **passed**: a small, real improvement |
| Does the public brain file (no video, no creator names) hold up? | Beat the fixed curve by duration on a period it had not seen | **Passed** on Jan-Jun 2026. Against a fresh 90-day average for its duration it lost in Jul-Dec 2025 and tied in Jan-Jun 2026 |
| Does reading the opening (a fixed sheet filled by Muse Spark Open) improve the number? | Better in both of two periods | **Passed**, by 1.4 to 2 people per 1,000 over the whole curve, with the rule sealed before measuring. One caveat: those sheets were written without a fixed temperature and 20 videos per call; the app asks for one video at temperature 0, and we have not measured that difference |
| How far off is the number? | No pass/fail rule: this sets the margin the panel shows | Off by 8.9 people of 100 on hidden creators, and 10.2 on hidden creators after the training period, against 10.4 and 11.7 for the fixed curve alone. That is an average, not a limit: in the harder check 4 in 10 videos miss by more. The panel says it is usually off by about 11 |
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

## Opening tactics

| Question | Rule written first | Result |
|---|---|---|
| Which ways of opening go with more retention and reach? ([`eval/tacticas_gancho.py`](../eval/tacticas_gancho.py)) | None: descriptive | What the review card notes about tactics comes from this. It compares different videos with each other, so it describes what happened, not a cause, and it is not a test of the rewrite |

## Not measured

- **Facebook's rules check.** It has no rule and no measurement. It reads what Muse Spark 1.3 wrote about what is on screen and what
  Muse Voice Transcribe heard, not the video file itself. Code drops any warning whose quote is not in that second of the video.
- **Whether the new opening keeps more people watching.** Never measured, and Retina does not promise it.
- **Any audience or human judgment of the new openings.** The judge is a model.
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
