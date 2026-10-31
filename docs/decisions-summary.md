# What happened, in order

An English summary of [`decisiones.md`](decisiones.md) and [`../BUILD-LOG.md`](../BUILD-LOG.md), which are the full record in Spanish.
Commit hashes in those two files refer to the history before it was recreated; [`hash-map.md`](hash-map.md) gives the new ones.

**26-27 Oct: from a list of curves to a first prediction.** We built the API wrapper with a spending cap, the video cutter, the
transcription and description services, and a first model of the 41-point retention curve. V-JEPA 2 frame features were tested and did
not help. The data set the limits: retention comes in whole points, so past the opening it cannot show where people leave. That promise
was dropped.

**28 Oct: Retina becomes an agent, and the judges say no twice.** The card became an agent with tools, a validator and rescue by Muse Spark
1.3, running on Muse Spark Open. A blind judge preferred one-pass cards over the agent's (27 to 12 in firm pairs), so the public version
writes the card in one pass. Spark watching two openings could not tell which loses more people. Looking at the video did not improve the
risk level, in either period.

**29 Oct: for any creator.** We asked whether Retina works for creators it has never seen. The first period failed; we changed the
comparison and said so; a second period passed with a small improvement. The public brain was trained without eligibility, out-of-scope topics,
out-of-scope topics or creator names. Reading the opening with a fixed sheet improved it a little. The traffic light failed its rule and left
the public version. A second version passed only after seeing the first fail, on periods already used, so it stays out as exploratory.

**30 Oct: from grading to fixing.** A grade is close to "simple image analyzers", so the core moved to producing and checking: Spark Open
rewrites the opening, Muse Image draws it, fixed rules and SAM 3.1 check it, and failures go back to Spark Open.

- The first test failed: 10 of 18. SAM did not know some words even when the drawing showed the object.
- We calibrated SAM's vocabulary on made-up drawings: 104 words work as they are, 10 through a general word, 53 can no longer be checked.
- The second test passed, 29 of 30. An audit later showed it is a regression test, not a validation: see [`results.md`](results.md).
- The organizers ruled that a small ridge layer is acceptable if the README explains it and the fitting details and weights are in the
  repo, and that an idea close to "simple image analyzers" is fine if the README and demo open with what makes it different. The number came
  back on by default.

**30 Oct, audit.** Five independent reviews rejected the entry as it stood. What came out of it:

- The training set is 23,710 videos, not "about 30,000".
- Facebook's curve seems to count only people past the first 3 seconds, so "out of every 100 people who start" was wrong.
- A difference smaller than the error was being shown as a difference. The margin is now measured and shown.
- The rule "bring the promise to the start" was emptying the video. Rule 3 changed to giving the first proof.
- The code was ordering the drawing to contain what SAM would look for. That order moved to the writer: the writer is told what will be
  looked for and must describe it, and the drawing comes from that text.
- Nobody had judged the openings. A model judge was added, with a sealed rule, on new videos. It is blind only in the side-by-side
  comparison.

**30 Oct, third test.** With the final instructions, the order to the drawing removed and 50 new videos, it passed all six conditions on its
first run: 29 of 30, 17 of 20, 10 of 10 far traps, and a model judge found 45 of 46 faithful, 45 of 46 leaving something for the rest of the
video (44 of 46 both), and preferred the new opening in 37 of 42 firm pairs. The judge is a model. Whether the new opening keeps more people was not measured.

**31 Oct, fourth test.** A review of the third test found two real openings worse than the original, frames 2 and 3 unchecked, and a judge that
had never seen a bad opening. The instructions became `apertura-v3`: a code rule rejects lists, the speaker's authority stays, Muse Spark 1.3
checks the other frames, Spark Open can say an opening already works, and the judge got a negative control. On 50 new videos, with the rule
sealed first, it passed all nine conditions on its first run: 27 of 30, 20 of 20, 10 of 10 far traps, 44 of 47 faithful, 46 of 47 leaving
something (43 of 47 both), 36 of 41 firm pairs, and the judge caught 10 of 10 planted lies and 9 of 10 planted summaries. The near trap fell
to 7 of 10, and "already works" never came up. Whether the new opening keeps more people was not measured.

## How to read the record

- A rule written first means written in `decisiones.md` before the run. From 29-Oct, sealed by a commit before measuring.
- What fails stays published and is not re-tuned on the same cases.
- Each test uses videos the previous ones did not touch. The second measurement's numbers are kept as they came out, including a trap
  frame that was badly set up.
