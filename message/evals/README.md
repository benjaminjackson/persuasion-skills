# Evals for `/message:judge`

Two commands:

```
python3 message/evals/run.py --calibrate     # Jev only, no claude, no cost of an agent run
python3 message/evals/run.py                 # end-to-end cases via claude -p
```

Run from the repository root, `/Users/ben/github/persuasion-skills`. Both need `TYPESAFE_API_KEY` set in the shell; source your `.env` first if it holds that key.

`run.py` is temporary, adapted from `writing-skills/draft/evals/run.py`. It reuses that file's `run_claude`, `parse_stream`, grading functions, and the `--tag`/`--case` handling. When `claude plugin eval` leaves early access, delete `run.py` and use that instead.

## `--calibrate`

Runs `scripts/judge.py fetch` and `scripts/judge.py score` against four hand-written pairs in `calibration/`: a **good** message and a **bad** message on the same topic, each with a hand-written `cards.json` next to it. It never calls `claude -p`, so it costs nothing but Jev's own price and runs in seconds to low minutes rather than the several minutes an end-to-end case takes.

For each pair it checks that the good message's overall score beats the bad message's, and prints a table of every axis, good minus bad, flagging any axis where the bad message scored as high or higher. A flagged axis means either the bad example does not actually violate that axis as badly as intended, or the rule itself is not measuring what it is meant to measure. Either way, that is worth reading closely before trusting the axis on a real message.

The four pairs:

| Pair | Good | Bad |
| --- | --- | --- |
| `equality-texas` | Verbatim, Equality Texas issues page, quoted in the C3 handbook as an effective narrative (C3 p16) | Leads with the problem, describes harm passively with no named villain, says what it is against rather than what it is for, hedges, and never asks for anything |
| `petra-falcon` | Verbatim, Petra Falcon's op-ed in the Arizona Republic on the federal budget, quoted in the C3 handbook (C3 p17 to p19) | Opens by rebutting the other side's claim, argues from budget jargon and statistics with no value behind them, and buries a hedged ask at the very end |
| `bail-memphis` | Verbatim, the WREG.com report on Black Lives Matter Memphis' "Bail Momma's Out" campaign, quoted in the C3 handbook (C3 p19 to p20) | Leads with a fear appeal, argues from the dollar cost of bail rather than from freedom or family, and asks for five different things at once |
| `drip` | A three-email fundraising sequence: one value throughout, the same named villain throughout, an ask that escalates from sign to share to show up, and each email opens by following up on the last | A three-email sequence with a different value in each email, no villain, and the identical vague ask repeated word for word in all three |

Each pair's good and bad message live in `calibration/<name>-good.md` and `calibration/<name>-bad.md`. `drip-good.md` and `drip-bad.md` are each a single file holding three emails separated by lines that are exactly `---`, scored with `--sequence`, so the pair also exercises the axes that compare adjacent messages in a series rather than only a single message on its own. The hand-written cards live next to each message as `<name>-good.cards.json` and `<name>-bad.cards.json`, keyed by message id the same way `fetch` assigns them (`m1` alone for a single message, `m1` through `m3` for a sequence).

An eval suite whose calibration has never been run is an opinion with a pass rate attached. Treat each calibration run as a test of the whole rulebook, not just of these four pairs: a run has already corrected the span rollup and two rule questions that the table caught.

## Default mode: end-to-end cases

```
python3 message/evals/run.py --case single-email
python3 message/evals/run.py --tag judge
python3 message/evals/run.py
```

Runs `claude -p` with `--plugin-dir` pointing at the `message` plugin, the same way the writing-skills suite runs `draft`. Two cases:

- **`single-email`**: a mediocre fundraising email (`fixtures/fundraising-email.md`), scored with no audience given, so `score` falls back to the rulebook's default. Graders check that `scripts/judge.py score` actually ran, that the reply names a path to a findings file, and that the reply names specific weak axes and shows at least one quoted original next to its written replacement, not just general advice.
- **`audience-given`**: the same fixture, but the prompt hands the skill an audience paragraph describing rural swing voters who are pocketbook- focused, distrust both parties' Washington rhetoric, and are turned off by jargon. The grader checks that the suggestions actually sound written for that audience: plain, concrete language, and no policy jargon.

Both cases are seeded with `fixtures/fundraising-email.md` through `case.yaml`'s `scaffold_script`, the same pattern the sibling suite uses for its fixtures.

## Why the end-to-end graders are mixed, not all judges

`tool_used` and `regex` check facts about what happened: did the script run, is a file path present. Only the shape and the audience-fit of the written reply need a judge, because only a reader can tell whether a suggestion is actually concrete, actually quotes the email, or actually sounds written for rural swing voters rather than for a policy briefing.

## The series row

The `drip` pair is the only one scored with `--sequence`, so it is the only one that produces a `series` key in `findings.json`. The runner reads `series.score` from it and prints one extra row under that pair's axes, because the series score sits beside the fourteen axes and is not blended into the overall. The individual pair results under `series.pairs` are left in the findings file for a person to read; the table reports only the rolled-up number.
