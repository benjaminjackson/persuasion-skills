---
type: regex
pattern: '[\w./-]*findings[\w./-]*\.json'
match: contains
target: last_message
---
Step 7 of `SKILL.md` says the reply must end with the path to `findings.json`, so the person can open the full breakdown themselves instead of trusting only what got said in chat. This checks for a path that contains "findings" and ends in ".json" somewhere in the final reply.

It is a character-sequence check, not a meaning check, on purpose: whether a path is present is a fact about the text, and a judge would be worse at answering it than a regular expression.
