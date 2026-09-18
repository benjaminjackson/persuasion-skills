# persuasion-skills

A Claude Code plugin marketplace with one plugin: **message**, which scores persuasive political messages against a rulebook built from movement messaging research, and tells you exactly what to change.

## Installation

```
claude plugin marketplace add benjaminjackson/persuasion-skills
claude plugin install message@persuasion-skills
```

## message

One skill: **judge**, invoked as `/message:judge`. It scores a message, a file of messages, or a whole site against a fourteen-axis rulebook, using TypeSafe's Jev to judge each rule and each message as a whole, and hands back concrete suggested rewrites for the weakest spots.

The judge assumes a progressive messenger. The rulebook it reads from takes a side, and so does every score it produces. It is not a neutral style checker; it is tuned to the messaging guidance below, all of it written for organizers and campaigns on the left.

### How it works

`/message:judge` runs a message through five steps:

1. **fetch** pulls the text to judge, from a local file, a URL (it will crawl a site up to two links deep, up to 25 pages), or a series of messages split on lines of `---`.
2. **cards** are written by Claude for each message: its ABT structure (and, but, therefore), its core value, its villain, its hero, its ask, a one-sentence summary, and the medium (social post, email, web page, op-ed or speech, ad or mailer, or other).
3. **score** sends every applicable rule question to Jev, batched to stay inside TypeSafe's rate limits, and writes a findings file with a 0 to 1 score per rule, per axis, and overall, plus the sentence-level violations and every raw Jev probability.
4. **suggestions** are concrete rewrites Claude drafts for the rules that scored worst, each one a specific sentence swapped for a specific replacement.
5. **verify** re-judges each suggested replacement with the same question the rule used, and reports whether the probability actually moved the right way.

When you judge a series of messages instead of one, the judge also checks consistency across the series: the same core value, villain, and hero from message to message, the same ABT structure, an ask that escalates rather than repeats, and each message following up on the one before it.

### The fourteen axes

1. **Values first**: lead with a shared value (family, community, fairness, freedom), not a problem.
2. **ABT structure**: ordinary world, one named problem, one solution the message stays in to the end (Olson's "and, but, therefore").
3. **Agency**: name who is choosing to cause harm; do not let problems appear to have no author.
4. **Aspiration**: be for something desirable, not only against something deplorable.
5. **Outcomes and lived experience**: describe what changes in a person's life, not the policy mechanism.
6. **Don't think of an elephant**: never repeat the other side's claim or frame, even to deny it.
7. **Inclusive we**: keep the reader inside the "we" the message speaks for; do not describe them looking in from outside.
8. **Frame choice**: reach for the frames that test well (opportunity, shared fate, freedom) and stay away from the ones that backfire (white privilege, personal responsibility, historical legacy as the lead).
9. **Audience lexicon**: use words a general reader already owns; movement jargon like "equity" or "intersectional" does not land.
10. **Confidence**: say what you will do, not what you will "seek to" or "strive to" do.
11. **The ask**: give one small, specific, doable action, not a call to "raise awareness."
12. **Real and felt**: show a specific person and a specific scene instead of telling the reader how to feel.
13. **Base, middle, opposition**: activate the base, persuade the middle, and alienate the opposition without firing them up; catch a message so hedged that no one on any side could disagree with it.
14. **Stickiness**: check whether a reader could repeat the message's value, ask, and villain back in one memorable line built around a single idea.

### Sources

The rulebook is drawn from:

- [Messaging This Moment](https://www.communitychange.org/wp-content/uploads/C3-Messaging-This-Moment-Handbook.pdf), a handbook from the Center for Community Change (C3)
- Kennedy, Fisher, and Bailey, "Framing in Race-Conscious, Antipoverty Advocacy," *Clearinghouse Review* 2010 (the Berkeley framing paper)
- Warpehoski, ["7 Principles of Community Organizing"](https://www.icpj.org/blog/wp-content/uploads/2016/07/7-Principles-of-Community-Organizing.pdf), Interfaith Council for Peace and Justice (ICPJ)
- [Framing Equality Toolkit](https://publicinterest.org.uk/FramingEqualityToolkit.pdf), ILGA-Europe and PIRC, 2017
- [*How to Test Your Communications*](https://www.ilga-europe.org/sites/default/files/testingguide.pdf), PIRC and ILGA-Europe
- [The Narrative Gym](https://businessofstory.com/wp-content/uploads/2021/05/THE-NARRATIVE-GYM-BOOK.pdf), Olson, 2020

### Before you run it

`/message:judge` needs [uv](https://docs.astral.sh/uv/) installed, and the environment variable `TYPESAFE_API_KEY` set to a valid TypeSafe API key. The script checks that the key is present; it never prints or logs its value.

## Author

Benjamin Jackson ([@benjaminjackson](https://github.com/benjaminjackson))
