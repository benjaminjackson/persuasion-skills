---
type: tool_used
tool: Bash
input_match: 'judge\.py\S*\s+score'
min: 1
---
The judge skill's whole pipeline runs through `scripts/judge.py`, and the `score` subcommand is the step that actually sends the rule questions to Jev. A run that reports a score without calling `score` made the score up.

This does not check that `fetch` ran too, only that scoring did, because `fetch` could in principle be skipped if the skill decided to build `messages.json` some other way. `score` is the one step nothing else can stand in for.

The pattern allows for characters between `judge.py` and `score`, because `SKILL.md` quotes the script path and the command therefore reads `judge.py" score`.
