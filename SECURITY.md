# Security

Found a flaw in Retina? Thank you. Please tell us in private, not in a public issue, so nobody can use it before it's fixed.

## How to report

Open the **Security** tab of this repository and press **Report a vulnerability**. Only the maintainers see your report.

Tell us:

- what the flaw lets someone do
- the steps to reproduce it
- the commit you tested and the file involved, if you know them

Don't include real keys, or videos and personal data that belong to someone else. A made-up example is enough.

## What's covered

- The code in this repository, on the `main` branch
- The panel and the local server
- The deployment files in `deploy/`, including the online demo setup

The Meta models and API, ffmpeg and other third-party software aren't ours to fix. Report those to their owners. If Retina uses them in an unsafe way, that one is ours, so tell us.

## What to expect

Retina is a small project, so we can't promise a response time or offer a reward. We read every report, and we'll tell you whether we confirmed the flaw and what we plan to do about it.

Please test only on your own copy. Don't test on an online demo you don't run, and don't try to reach other people's videos.
