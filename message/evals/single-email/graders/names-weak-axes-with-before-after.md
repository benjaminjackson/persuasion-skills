---
type: llm
focus: last_message
weight: 1
---
`SKILL.md` promises a specific shape for the reply: the overall score, the three weakest axes with what is dragging each one down, and the top suggestions, each shown as the original span next to its replacement.

Read the reply below and answer:

1. Does it name specific axes (for example "values-first", "the ask", "agency") rather than only a vague general impression such as "this could be more persuasive"?
2. For at least one weak spot, does it quote the actual offending text from the email, not just describe the problem in the abstract?
3. For at least one suggestion, does it show a replacement, in other words a concrete rewritten version of that same span, not just advice like "add more urgency" with nothing written out?

PASS if the reply names specific axes and shows at least one quoted original next to a written replacement for it.

FAIL if the reply only describes problems in general terms, never quotes the email's own text, or never shows a rewritten version of anything.
