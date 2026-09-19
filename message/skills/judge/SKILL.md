---
name: judge
description: >-
  Score a persuasive political message against the rulebook in
  references/rules.md, using Jev (TypeSafe's System One judgment model) to
  answer each rule's question, and turn the failures into concrete rewrite
  suggestions. Assumes a progressive messenger. Works on pasted text, a
  local file, a URL, a whole site (crawled), or an ordered series of
  messages read from one file. Trigger on "judge this message", "score this
  message", "make this more persuasive", "is this persuasive", "check this
  messaging", "review this campaign email", or "audit this candidate
  website".
---

# Judge a persuasive message

This skill runs a message, or a set of them, through the rulebook at [references/rules.md](references/rules.md) and reports where it holds up and where it does not, with a rewrite for every place it does not. The rulebook is the only source of truth for what gets measured: read it before scoring anything you have not scored before, because the rule ids, the axis list, and the state shapes sent to Jev all live there, not in this file.

All the real work runs through `scripts/judge.py`, a single script with four subcommands: `fetch`, `score`, `verify`, and `rules`. Call it by its full path and leave the working directory where it is, which is the person's own project. The script finds the rulebook beside itself, so it does not care what the working directory is, and the files it writes then land somewhere the person can find them instead of inside the installed plugin:

```
uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/judge/scripts/judge.py" <subcommand> ...
```

Write `messages.json`, `cards.json`, `findings.json`, `suggestions.json` and `verified.json` to a scratch directory you own, and give every `--out` an absolute path. Never write them next to the script.

## 1. Gather the input

Figure out what you are judging before you touch the script:

- **Pasted text.** Write it to a local file first (`fetch` reads files, URLs, or stdin, not a string on the command line).
- **A local file.** Use its path directly.
- **A URL.** `fetch` crawls same-domain links up to depth 2 and 25 pages by default; pass `--depth 0` for just that one page.
- **A whole site.** Same as a URL. The defaults already crawl it, two links deep and up to 25 pages; raise `--depth` and `--max-pages` to go wider. Confirm with the person first if the site looks large, because a full crawl of a many-page site is the case that later spawns subagents in step 3.
- **An ordered series** (a sequence of ads, emails, or posts meant to be read in order). Put each message in one local file separated by lines that are exactly `---`, then pass `--sequence`.

Ask for the audience if none was given, but don't block on it: the rulebook defines a default audience (the general American public, judged against what is broadly resonant with most Americans), and `score` falls back to it on its own when you omit `--audience`. If the person gives you a sentence describing the audience, pass it with `--audience`. If they hand you a longer brief, save it to a file and pass `--audience-file`.

## 2. Fetch

```
uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/judge/scripts/judge.py" fetch <source> --out <scratch>/messages.json
```

Add `--sequence` for an ordered series read from one local file, or `--depth`/`--max-pages` to change the crawl limits for a site. This writes `messages.json`: one entry per message, each with an id, its sentences already split, and, for a URL, the page title and address.

## 3. Read messages.json and write cards.json

For every message, read its text and write one card:

- **`abt`**: a one-sentence And, a one-sentence But, a one-sentence Therefore, in the message's own words.
- **`core_value`**: the value the message leads with or stands for.
- **`villain`**: who or what it blames, if anyone.
- **`hero`**: who it says can fix the problem, if anyone.
- **`ask`**: what it wants the reader to do, if anything.
- **`summary`**: one sentence, written the way an ordinary reader would repeat the message to a friend.
- **`medium`**: exactly one of `social post`, `email`, `web page`, `op-ed or speech`, `ad or mailer`, `other`, judged from the source and the text.

Write only what the message actually says. A card is a reading of the message, not an improved version of it; inventing a value or an ask the text does not support breaks every rule question that reads the card afterward. Save the result as `cards.json`, keyed by message id, matching the shape `score` expects.

**Large sites.** When `messages.json` holds more than 5 pages, don't write every card yourself. Spawn one `sonnet` subagent per page, in parallel, each with: the one page's text, the card fields above, and an instruction to write its card as a JSON fragment to its own file and to end its reply with that file's path. A subagent's final reply comes back to you when it finishes, so do not ask it to send you a message some other way. Once every subagent has finished, read the fragments and merge them into one `cards.json` keyed by message id.

## 4. Score

```
uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/judge/scripts/judge.py" score <scratch>/messages.json <scratch>/cards.json --audience "<audience>" --out <scratch>/findings.json
```

Use `--audience-file <path>` instead of `--audience` when the brief is longer than a sentence. Leave both off to use the rulebook's default audience. This sends every applicable rule question to Jev and writes `findings.json`: an overall score and a per-axis, per-rule breakdown for each message, plus series-level findings (paired messages, one-ask checks) when the source was a sequence or a site.

## 5. Read findings.json and write suggestions.json

The file is keyed by message id under `messages`. Each message holds its `overall` score and an `axes` object; each axis holds its own `score` and a `rules` object; each rule holds a `score`, an `na` flag, the raw Jev answer, and, for a span rule, a `violations` list of the sentences that failed with their index, text, and probability. Read the weak axes with one call rather than exploring the file:

```
jq -r '.messages.m1.axes | to_entries | map({axis: .key, score: .value.score}) | sort_by(.score) | .[] | "\(.axis) \(.score)"' <scratch>/findings.json
```

For every span-level violation and every message-level rule that failed, write one entry:

- `message_id`, `rule_id`, `sentence_index` (span rules only)
- `original`: the exact offending span, quoted
- `replacement`: a rewrite in the message's own voice that fixes what the rule flagged
- `note`: one sentence naming the rule and its source page from [references/rules.md](references/rules.md) (for example, "C3 p4")

See **Rules for suggestions** below before writing any of these.

Beyond the span-level list, add message-level structural notes where the findings call for them: reorder to lead with the value, add or cut an ask, cut a rebuttal to the opposition's frame, name the villain plainly. For a series or a site, add series notes too: where the same value, villain, or hero should carry across messages, where the ask should escalate, where a follow-up is missing.

Save the result as `suggestions.json`. Apply the same subagent-per-page rule from step 3 for a large site: each subagent writes its message's suggestions to its own fragment file and ends its reply with the path, then you merge.

## 6. Verify

```
uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/judge/scripts/judge.py" verify <scratch>/findings.json <scratch>/suggestions.json --out <scratch>/verified.json
```

This re-judges each replacement with the same question that flagged the original span and reports the before and after probability. Drop any suggestion `verify` marks as not improved from what you report; keep it in `verified.json` but don't put it in front of the person. Note in your summary that the rest were checked against Jev, not just written by hand.

## 7. Reply in chat

No report file. Reply directly with:

- The overall score.
- The three weakest axes, one line each: the axis name and what is dragging it down.
- The top few suggestions, each with the original span and its replacement.
- Series findings, if the source was a sequence or a site.
- The path to `findings.json`.

Before reporting a difference between two overall scores, establish the noise floor: score the same message twice, unchanged, and take that spread as the floor. Differences below it are not findings. A one-sentence edit is generally below it, so report "no measurable difference" rather than ranking to four decimals. Note that the `confidence` axis measures how confident the message sounds, not how reliable the measurement is.

## Rules for suggestions

- Keep the author's voice. Match their register and sentence length; a suggestion that sounds like a different writer is not a fix.
- One change per suggestion. Don't bundle a value fix and an ask fix into the same sentence.
- Never introduce the opponent's frame, even to rebut it, and never add a hedge ("some might say", "while it's true that") the original didn't have.
- Cite the rule id in every suggestion's note, so the person can look up the reasoning in the rulebook.

## Cost

Jev input costs 4.2 cents per million tokens; output is free. A typical web page runs well under a cent to score end to end.

## Also available

`uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/judge/scripts/judge.py" rules` prints every parsed rule (id, axis, level, type, weight) as a table. Run it if a `score` call errors on a rule id, or to sanity-check the rulebook after it changes.
