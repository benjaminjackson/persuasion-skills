# Rulebook for `/message:judge`

This file is the single source of truth for what the judge measures. Every rule has three parts: the guidance in plain words with its source, embrace and replace examples, and a fenced `json` block that holds the exact question sent to Jev (TypeSafe's System One model). The script `scripts/judge.py` parses the `json` blocks. Nothing about a rule lives anywhere else, so editing this file changes the judge.

The judge assumes a progressive messenger. The sources take sides and so does the rulebook.

## Sources and how pages are cited

| Key | Document | Page convention |
| --- | --- | --- |
| C3 | Shenker-Osorio, *Messaging This Moment* handbook (Center for Community Change) | PDF page (each PDF page is a two-page spread) |
| FR | Kennedy, Fisher, Bailey, "Framing in Race-Conscious, Antipoverty Advocacy", *Clearinghouse Review* 2010 | PDF page |
| ORG | Warpehoski, "7 Principles of Community Organizing" (ICPJ) | PDF page |
| FET | ILGA-Europe and PIRC, *Framing Equality Toolkit* 2017 | PDF page |
| TEST | PIRC and ILGA-Europe, *How to Test Your Communications* | PDF page |
| GYM | Olson, *The Narrative Gym* 2020 | Printed page (PDF page = printed page + 7) |

## How the script reads this file

Every fenced `json` block is either the axis table (one block, `"axes"` key) or a rule. Rule fields:

| Field | Meaning |
| --- | --- |
| `id` | `<axis>.<rule>`. Stable. Findings reference it. |
| `axis` | One of the fourteen axis keys, or `series`. |
| `level` | What the state is. `message`: the whole message with `medium` and `audience`. `span`: one sentence at a time, the question template uses `{i}` for the sentence index inside `sentences`. `card`: the message plus the card Claude wrote for it (one-sentence ABT, core value, villain, hero, ask, summary). `pair`: the cards of two messages, an adjacent pair from a sequence or one page against a site's homepage. |
| `type` | `noul`, `score`, or `choice`. |
| `bad` | `true` when a yes or a high score means a violation. The script inverts these before rollup. |
| `weight` | Relative weight inside the axis. Any positive number. |
| `penalty` | Span rules only. Each violating sentence subtracts this much from the rule's score, floor zero. Default 0.25, so four violations zero the rule. The count is first scaled down to a message of eight sentences, so a long message is not punished merely for having more sentences to trip on. A message of eight sentences or fewer is scored by the plain count. |
| `detector` | Span rules only, optional. A regex, matched without regard to case so that a lowercase pattern still catches the word at the start of a sentence. When present, only sentences that match are sent to Jev, everything else passes. Use it for lexicon rules. Wrap any part that has to match case in `(?-i:...)`, the way the acronym rule does, because an uppercase-only pattern otherwise matches every word. |
| `scope` | Span rules only, optional. `opening` sends only the first three sentences. `closing` sends only the last three. |
| `min_words` | Skip the rule and mark it not applicable when the message is shorter. |
| `media` | Skip the rule unless the inferred medium is in this list. |
| `scores` | Choice rules only. Maps each option to a 0 to 1 score. |
| `question` | The Jev question: `instructions` plus `criteria`. Sent verbatim. |

State shapes the script builds:

- `message` level: `{"medium": "...", "audience": "...", "message": "..."}`. When no audience was given, `audience` is "the general American public; judge against what is broadly resonant with most Americans".
- `span` level: `{"audience": "...", "sentences": ["...", "..."]}`. Sentences are split in code. One question per sentence per rule, batched to stay under the token budget.
- `card` level: `{"message": "...", "card": {"abt": {"and": "...", "but": "...", "therefore": "..."}, "core_value": "...", "villain": "...", "hero": "...", "ask": "...", "summary": "..."}}`. Claude writes the card from the message before scoring, using only what the message says.
- `pair` level: `{"earlier": <card>, "later": <card>}`. For a sequence these are adjacent messages in the order they were sent. For a site, `earlier` is the homepage card and `later` is one other page's card, so the same rules serve both shapes.

Rollup, all in code: each rule becomes a 0 to 1 pass score. A `noul` is the probability, inverted when `bad`. A `score` is the level position divided by the top level, inverted when `bad`. A `choice` is the probability-weighted sum of `scores`. Span rules become `max(0, 1 - violations * penalty * min(1, 8 / sentences_in_scope))` where a violation is a sentence with a Jev probability of 0.5 or higher, and `sentences_in_scope` is the whole message unless the rule sets `scope`. The eight is a reference length: it keeps the plain count for a short message and scales a long one down, because without it any span rule floors at zero after four hits and a long, good message loses to a short, weak one. Each axis is the weighted mean of its rule scores blended with its holistic Score by `holistic_share`. The overall is the weighted mean of the axes. All raw probabilities stay in the findings file.

## Axes

```json
{
  "axes": {
    "holistic_share": 0.4,
    "weights": {
      "values-first": 1.2,
      "abt": 1.0,
      "agency": 1.0,
      "aspiration": 1.0,
      "outcomes": 0.8,
      "no-elephant": 1.2,
      "inclusive-we": 1.0,
      "frame": 1.0,
      "lexicon": 0.8,
      "confidence": 0.5,
      "ask": 1.2,
      "real": 0.8,
      "segments": 1.0,
      "stickiness": 0.8
    }
  }
}
```

The weights are a starting point. The calibration evals decide whether they hold.

---

## Axis 1. Values first (`values-first`)

Lead with a shared value, not a problem. "Americans got 99 problems and they don't want yours." Family tested strongest, then community, fairness, and freedom (C3 p4). The framing paper says the same from the other direction: a brief statement of values gives the listener a road map, and a solution stated early prevents compassion fatigue (FR p13, p15). The toolkit calls it speaking to people's best self: remind them they are good and want good things (FET p29, p31). C3's effective narratives all begin in shared value and return to it at the end (C3 p12, p16).

Embrace: "Most of us seek to treat others the way we want to be treated." "No matter our differences, most of us want to be able to provide for our families." "America is a nation founded on an ideal: that all are created equal."

Replace: "Our treatment of undocumented immigrants and refugees is horrendous." "The criminal justice system imprisons African Americans and Latinos at alarming rates." "Our broken immigration system tears families apart." (C3 p4)

### 1.1 Opens with a shared value

The first thing the reader meets is a value most people hold, stated in plain words. Not a problem, a statistic, a crisis, or an attack on the other side.

```json
{
  "id": "values-first.opens-with-value",
  "axis": "values-first",
  "level": "message",
  "type": "noul",
  "weight": 2,
  "question": {
    "instructions": "Do the first two sentences of `message` state a value that most people share, such as family, fairness, freedom, community, opportunity, or treating others as you want to be treated, before any problem, statistic, threat, or criticism of an opponent is mentioned?",
    "criteria": {
      "true": "The opening states a widely shared value or aspiration in plain words. A problem may follow, but the value comes first.",
      "false": "The opening leads with a problem, a crisis, a statistic, an attack on an opponent, or a description of the organization, and any value comes later or not at all."
    }
  }
}
```

### 1.2 The value is named, not implied

Readers should be able to say what the message stands for. A value hidden inside policy language does not count.

```json
{
  "id": "values-first.value-named",
  "axis": "values-first",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "question": {
    "instructions": "Does `message` name, in plain everyday words, the value it stands for, so that a reader could repeat that value in one phrase?",
    "criteria": {
      "true": "A value such as family, fairness, freedom, dignity, safety, community, or opportunity is stated outright, for example 'everyone who works for a living ought to earn a living'.",
      "false": "The value is only implied by policy positions or problems described, and a reader would have to guess what the message stands for."
    }
  }
}
```

### 1.3 Returns to the value

Effective narratives close on the value or the solution, not on the problem (C3 p12, Equality Texas example p16).

```json
{
  "id": "values-first.returns-to-value",
  "axis": "values-first",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "min_words": 80,
  "question": {
    "instructions": "Do the last two sentences of `message` restate a shared value or the good outcome being sought, rather than ending on a problem, a warning, or an attack?",
    "criteria": {
      "true": "The message ends on the value, the vision, or the call to act toward it.",
      "false": "The message ends on a problem, a statistic, a threat, or criticism of an opponent."
    }
  }
}
```

### 1.4 Holistic

```json
{
  "id": "values-first.holistic",
  "axis": "values-first",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "How well does `message` lead with shared values rather than problems?",
    "criteria": [
      "Leads with a problem, crisis, or attack and never names a shared value",
      "Names a shared value somewhere, but the problem or the organization comes first and dominates",
      "Opens with a shared value, then moves to the problem, but the value is generic or does not connect to the rest",
      "Opens with a clear shared value in plain words, the problem is framed as an attack on that value, and the message returns to the value at the end"
    ]
  }
}
```

---

## Axis 2. ABT structure (`abt`)

Olson's template: `___ AND ___ BUT ___ THEREFORE ___` (GYM p23). The AND material is the ordinary world plus what is at stake, material everyone can agree with, "even a climate skeptic" (GYM p36 to p38). The main character belongs in the AND, not sprung on the reader at the solution (GYM p48 to p50). The BUT is one problem, named once, and the message should get to it fast (GYM p52, p72). Headline before details: WHAT then HOW, in both the problem and the solution (GYM p65). The THEREFORE is the solution, and the message stays in consequence mode to the end, as King's second half is all "therefore" (GYM p53 to p54). Two failure shapes: AAA, a list of facts with no problem, which bores; and DHY, despite/however/yet, more than one contradiction, which confuses (GYM p52, p71). Words of contradiction (but, despite, however, yet, contrary) and consequence (therefore, thus, as a result) do not belong in the AND material (GYM p51). Everyone on a team should write the same ABT for the message, or there is a messaging problem (GYM p75). This axis maps onto C3's arc: shared value, then problem with a named agent, then "that's why we're..." (C3 p12).

Embrace: "There are 50 acres of woods next to my house AND they generate $2 million a year in local business, BUT the woods are unprotected, THEREFORE we are changing the law by working with politicians, starting petitions, organizing a non-profit, and running advertisements." (GYM p67, minus the money stake, which the toolkit rules out for our purposes, see axis 8.)

Replace: "Contrary to previous research..." as an opening (GYM p51). "BUT a developer is planning to destroy the woods, BUT some of the woods may be spared, THEREFORE..." (GYM p53). "THEREFORE we're now working with politicians, we're starting petitions, we're organizing a non-profit, and we're running advertisements, all of which will lead to a change in the law." (details before the headline, GYM p65)

### 2.1 Opens in agreement

```json
{
  "id": "abt.opens-in-agreement",
  "axis": "abt",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "min_words": 60,
  "question": {
    "instructions": "Before any problem is raised, does `message` open with a setup that nearly everyone, including people who disagree with the author, would accept as true or agree with?",
    "criteria": {
      "true": "The opening describes a shared situation, value, or fact that is not in dispute, and only afterwards introduces a problem.",
      "false": "The opening itself is the problem, a contested claim, or a contradiction of something."
    }
  }
}
```

### 2.2 No contradiction words in the opening

Code sends only the first three sentences that contain a contradiction or consequence word. Jev decides whether the word is doing structural work.

```json
{
  "id": "abt.opening-contradiction",
  "axis": "abt",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 0.5,
  "scope": "opening",
  "detector": "\\b(but|however|despite|yet|contrary|nevertheless|therefore|thus|as a result|in conclusion)\\b",
  "penalty": 0.5,
  "min_words": 60,
  "question": {
    "instructions": "Does `sentences[{i}]` introduce a problem, a contradiction, or a conclusion, rather than describe a shared starting point?",
    "criteria": {
      "true": "The sentence turns against something, raises a problem, or draws a conclusion, for example 'But the system is rigged' or 'Therefore we must act'.",
      "false": "The sentence describes a situation, value, or fact without turning against anything, even if it contains the word 'but' in a non-structural way such as 'nothing but'."
    }
  }
}
```

### 2.3 Stakes before the problem

"I have 17 vacuum cleaners, BUT one is broken" is not a problem. Say why it matters before the BUT (GYM p37 to p38).

```json
{
  "id": "abt.stakes-before-problem",
  "axis": "abt",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "min_words": 60,
  "question": {
    "instructions": "Before the central problem is introduced, does `message` make clear why the subject matters to the reader, using specifics rather than general claims of importance?",
    "criteria": {
      "true": "The reader learns what is at stake, in concrete terms, before the problem lands.",
      "false": "The problem arrives before the reader has any reason to care, or the stakes are stated only in vague terms such as 'this is important'."
    }
  }
}
```

### 2.4 One central problem

```json
{
  "id": "abt.single-problem",
  "axis": "abt",
  "level": "message",
  "type": "noul",
  "weight": 1.5,
  "min_words": 60,
  "question": {
    "instructions": "Does `message` present one central problem, rather than two or more separate problems competing for attention?",
    "criteria": {
      "true": "There is one problem the whole message turns on. Other details serve that problem.",
      "false": "The message raises two or more distinct problems that pull in different directions, or it lists many problems without choosing one."
    }
  }
}
```

### 2.5 Problem followed by a solution

```json
{
  "id": "abt.has-therefore",
  "axis": "abt",
  "level": "message",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "After stating a problem, does `message` present a solution or a consequence, something that is done or should be done because of the problem?",
    "criteria": {
      "true": "The problem leads to a stated solution, plan, or action.",
      "false": "The message stops at the problem, or the solution is missing or so vague it could not be acted on."
    }
  }
}
```

### 2.6 Stays in consequence mode

```json
{
  "id": "abt.stays-in-therefore",
  "axis": "abt",
  "level": "message",
  "type": "noul",
  "bad": true,
  "weight": 0.75,
  "min_words": 120,
  "question": {
    "instructions": "After `message` has introduced its solution, does it go back to raising new problems, new complaints, or new contradictions instead of staying with the solution and the action?",
    "criteria": {
      "true": "New problems or contradictions appear after the solution has been introduced.",
      "false": "Once the solution appears, the rest of the message stays with the solution, its benefits, and the action."
    }
  }
}
```

### 2.7 Headline before details

```json
{
  "id": "abt.what-before-how",
  "axis": "abt",
  "level": "message",
  "type": "noul",
  "weight": 0.75,
  "min_words": 80,
  "question": {
    "instructions": "When `message` states its problem and its solution, does it give the bottom line first and the details after, rather than listing details that build up to the point?",
    "criteria": {
      "true": "The problem is stated as a headline and then explained; the solution is stated as a headline and then explained. For example 'The forest is now severely degraded, due to fifty years of...'",
      "false": "The message walks through causes, steps, or history before finally saying what the problem or solution is. For example 'Over fifty years trees were cleared, pollution rose, and parts were sold, leaving the forest degraded'."
    }
  }
}
```

### 2.8 Main character introduced early

```json
{
  "id": "abt.main-character-early",
  "axis": "abt",
  "level": "message",
  "type": "noul",
  "weight": 0.75,
  "min_words": 80,
  "question": {
    "instructions": "Is the person, group, or thing that the solution in `message` centers on already present before the solution is introduced?",
    "criteria": {
      "true": "The solution's main subject, such as the people who will benefit or the program being proposed, appears in the setup or the problem.",
      "false": "The solution introduces a person, group, program, or organization for the first time at the end."
    }
  }
}
```

### 2.9 The card's ABT is faithful

Claude writes a one-sentence ABT for each message. This checks that the ABT is what the message actually says, not a better message Claude wished it said.

```json
{
  "id": "abt.card-faithful",
  "axis": "abt",
  "level": "card",
  "type": "noul",
  "weight": 0.5,
  "question": {
    "instructions": "Is `card.abt` a faithful one-sentence compression of `message`, using only claims, problems, and solutions that `message` itself states?",
    "criteria": {
      "true": "Every part of the ABT can be traced to something the message says, and nothing important the message argues is contradicted.",
      "false": "The ABT adds a value, a problem, a villain, or a solution the message does not state, or it changes the message's argument."
    }
  }
}
```

### 2.10 Holistic

```json
{
  "id": "abt.holistic",
  "axis": "abt",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "Which narrative shape does `message` have?",
    "criteria": [
      "A list of facts, points, or complaints with no single problem and no turn: and, and, and",
      "Several problems or contradictions competing, so the reader cannot tell which one matters: despite, however, yet",
      "A recognizable setup, problem, and solution, but one part is weak, buried, or out of order",
      "A clean arc: an opening everyone agrees with, one clear problem, and a solution the reader can act on, in that order"
    ]
  }
}
```

---

## Axis 3. Agency (`agency`)

Problems do not have no origin. "The gap didn't widen of its own accord." Lawmakers implement policies and can choose otherwise. People "lose" keys and wallets; politicians take or confiscate health insurance. Use verbs of choice: choose, decide, eliminate, confiscate, rig, take (C3 p5). Our people should also appear as subjects who act, not only as objects of harm (C3 p5, Petra Falcon example p19).

Embrace: "CEOs decided to pay people less." "Lawmakers took our coverage." "Politicians put up barriers to prosperity for communities of color." "Greedy few rigged the game." "Corporations take from working people." (C3 p5)

Replace: "Jobs were lost." "People will lose coverage." "The income gap has widened." "Health disparities are increasing." "The unemployment rate rose." "Conditions persist." "[Name of group] continues to face..." "Systemic inequities." "[Economic] inequality." (C3 p5)

### 3.1 Harm with no one doing it

```json
{
  "id": "agency.hidden-agent",
  "axis": "agency",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 2,
  "penalty": 0.25,
  "question": {
    "instructions": "Does `sentences[{i}]` describe a harm, loss, or worsening condition without naming who caused it or chose it?",
    "criteria": {
      "true": "The sentence states a harm, a loss, or a worsening condition, and gives it no actor: passive voice with no agent, a condition that 'rose', 'widened', 'persists', or 'is increasing', or people who 'lost' something as if by accident. Examples: 'Jobs were lost.' 'The wealth gap has widened.' 'Families are losing coverage.'",
      "false": "The sentence states no harm at all, or it names the person, group, or institution that caused the harm. Answer false for a statement of fact, a number, a value, an opinion, an eligibility rule, a good thing, or an action somebody is taking. Answer false for a person telling their own story in their own words, because that is testimony and not the message's framing. Examples of false: 'It's not moral.' 'Sixty of those women are in for misdemeanor crimes.' 'The group launched an effort to pay bail.' 'I had to go to court five or six times.' 'Lawmakers took our coverage.'"
    }
  }
}
```

### 3.2 A villain is named

```json
{
  "id": "agency.names-villain",
  "axis": "agency",
  "level": "message",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "Does `message` name a specific person, group, or institution that chose to cause the central problem, such as named politicians, CEOs, corporations, or lawmakers?",
    "criteria": {
      "true": "A specific actor is identified as having decided, chosen, or done the thing that causes the problem.",
      "false": "The problem is attributed to no one, to abstractions such as 'the system' or 'inequality', or to forces described as natural or inevitable."
    }
  }
}
```

### 3.3 A hero is named

```json
{
  "id": "agency.names-hero",
  "axis": "agency",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "question": {
    "instructions": "Does `message` show the people it speaks for, such as working people, families, neighbors, or 'we', doing something: joining together, standing up, building, deciding, or winning?",
    "criteria": {
      "true": "The message's own people appear as subjects who act, not only as people things happen to.",
      "false": "The message's people appear only as victims, beneficiaries, or recipients, or do not appear at all."
    }
  }
}
```

### 3.4 Holistic

```json
{
  "id": "agency.holistic",
  "axis": "agency",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "How clearly does `message` show who causes the problem and who acts to solve it?",
    "criteria": [
      "Problems happen on their own; no one causes them and no one acts",
      "A cause is hinted at, such as 'the system' or 'special interests', but no specific actor chooses anything, and our people only suffer",
      "A specific villain chooses the harm, or our people act, but not both",
      "A specific villain chooses the harm and our people act to change it, both in active verbs"
    ]
  }
}
```

---

## Axis 4. Aspiration (`aspiration`)

Create something good, don't merely reduce something bad. "Fixing", "reforming", "improving", "mitigating" may be accurate, but they suppress motivation. Be for something desirable rather than only against something deplorable. "A 'no' without a 'yes' leads listeners to think we're just playing politics as usual." "Martin Luther King had a dream, not a complaint." (C3 p6)

Embrace: "Create an immigration process." "Paid enough to provide for family, able to set kids off to a bright future." "People who work for a living ought to earn a living." "Create safe and healthy communities." "Protect our children's health." (C3 p6)

Replace: "Fix our broken immigration system." "Improve wages and working conditions." "Increase access to paid family leave." "Stop/mitigate/slow down climate change." "This is not an adequate child care plan." (C3 p6, p8)

### 4.1 Goal stated as reducing a bad thing

```json
{
  "id": "aspiration.reduce-bad",
  "axis": "aspiration",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1.5,
  "penalty": 0.25,
  "detector": "\\b(fix|fixing|reform|reforming|mitigat\\w*|reduc\\w*|improv\\w*|combat\\w*|fight\\w*|tackl\\w*|address\\w*|stop|stopping|end|ending|slow|broken|curb\\w*|prevent\\w*|protect\\w* against)\\b",
  "question": {
    "instructions": "Does `sentences[{i}]` describe a goal only as fixing, reducing, stopping, reforming, or fighting a bad thing, without naming the good thing that would exist instead?",
    "criteria": {
      "true": "The sentence's goal is the absence or reduction of something bad, for example 'fix our broken immigration system', 'reduce poverty', 'combat climate change', and it does not say what people would have instead.",
      "false": "The sentence names the good thing being created, for example 'create an immigration process', 'everyone paid enough to make ends meet', or the sentence is not about a goal."
    }
  }
}
```

### 4.2 Says what it is for

```json
{
  "id": "aspiration.states-the-yes",
  "axis": "aspiration",
  "level": "message",
  "type": "noul",
  "weight": 2,
  "question": {
    "instructions": "Does `message` describe, in concrete terms, the good thing it wants to exist: what people would have, do, or be able to count on if it succeeded?",
    "criteria": {
      "true": "The message paints the desired outcome, for example 'every working parent paid enough to set their kids off for a bright future'.",
      "false": "The message only opposes, criticizes, or promises to fix or reduce something, and never says what the good result looks like."
    }
  }
}
```

### 4.3 Not only a no

```json
{
  "id": "aspiration.not-only-a-no",
  "axis": "aspiration",
  "level": "message",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "question": {
    "instructions": "Is `message` mainly a denunciation of something the other side did or proposed, with no attractive alternative of its own?",
    "criteria": {
      "true": "The message spends itself calling a plan, a person, or a policy bad, inadequate, or dangerous, and offers no fleshed-out alternative.",
      "false": "The message proposes or describes its own alternative, or is not a response to an opponent at all."
    }
  }
}
```

### 4.4 Holistic

```json
{
  "id": "aspiration.holistic",
  "axis": "aspiration",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "Is `message` for something or only against something?",
    "criteria": [
      "Only against: it denounces or promises to stop, fix, or reduce a bad thing and never says what it wants instead",
      "Mostly against, with the good outcome mentioned in passing or in policy language",
      "For something concrete, but the language still leans on fixing and reducing",
      "Clearly for a concrete good outcome, described so the reader can picture it, and the bad thing is named as what stands in its way"
    ]
  }
}
```

---

## Axis 5. Outcomes and lived experience (`outcomes`)

Focus on outcomes, not process. "Minimum wage increase" and "paid family leave" name policy; "people are paid enough to make ends meet" and "you're at your new baby's side" name outcomes. In health care the lived concern is not eligibility and benefits, it is seeing a doctor, getting treatment, affording medicine. We shield humans from view by calling them "beneficiaries", "enrollees", "eligible individuals". "Working people" beats "workers" and "the middle class". Name illness: strep throat, cancer, not "medical conditions" (C3 p7, p15).

Embrace: "Food, housing, medical care." "Make ends meet, retire in dignity, prevent and treat illness." "Paid time to care for loved ones." "Being there for family isn't negotiable." "[Program] ensures that working people struggling to make ends meet can feed their families." "Whether it's routine like strep throat or scary like cancer..." (C3 p7, p15)

Replace: "Safety net." "Entitlements." "Paid family and medical leave." "X policy." "Gap between rich and poor." "[Program] is a key work support program that helps those in low paying jobs get by." "Eligible individuals, recipients, enrollees." "Block grants." "Coverage, access to coverage." "Medical/health conditions." (C3 p7)

### 5.1 Policy or process instead of outcome

```json
{
  "id": "outcomes.process-language",
  "axis": "outcomes",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1.5,
  "penalty": 0.25,
  "question": {
    "instructions": "Does `sentences[{i}]` describe a goal or a harm by naming a policy, program, or procedure, without saying what it means in a person's daily life?",
    "criteria": {
      "true": "The sentence's subject is a mechanism: a bill, a funding formula, eligibility, enrollment, block grants, a wage increase, access to coverage, a program name, and the human result is not stated. Examples: 'We support a minimum wage increase.' 'Cuts to Medicaid would reduce access to coverage.'",
      "false": "The sentence says what people would have, do, or go through, for example 'paid enough to make ends meet', 'see a doctor without going broke', or the sentence is not about a goal or harm."
    }
  }
}
```

### 5.2 People hidden behind labels

```json
{
  "id": "outcomes.dehumanizing-labels",
  "axis": "outcomes",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "penalty": 0.34,
  "detector": "\\b(beneficiar\\w+|enrollee\\w*|recipient\\w*|eligible individual\\w*|the vulnerable|vulnerable populations?|populations?|consumers?|clients?|caseloads?|the poor|low-income individuals?|the elderly|the disabled|the homeless)\\b",
  "question": {
    "instructions": "Does `sentences[{i}]` refer to people by an administrative or categorical label such as beneficiaries, enrollees, recipients, populations, the vulnerable, or the poor, instead of as people, families, neighbors, or working people?",
    "criteria": {
      "true": "People appear as a category or a caseload.",
      "false": "People appear as people: families, kids, seniors, neighbors, working people, someone's mother, or the sentence uses the label to quote or describe an opponent's language."
    }
  }
}
```

### 5.3 "Workers" and "the middle class"

```json
{
  "id": "outcomes.working-people",
  "axis": "outcomes",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 0.5,
  "penalty": 0.25,
  "detector": "\\b(workers?|the middle class|middle-class|workforce|labor force)\\b",
  "question": {
    "instructions": "Does `sentences[{i}]` use 'workers', 'the workforce', or 'the middle class' to refer to the people the message speaks for?",
    "criteria": {
      "true": "The sentence refers to its own people as workers, the workforce, or the middle class.",
      "false": "The sentence says working people, people who work for a living, families, or a specific kind of person, or the word is part of a proper name or a quotation."
    }
  }
}
```

### 5.4 Abstract harm instead of a felt one

```json
{
  "id": "outcomes.abstract-harm",
  "axis": "outcomes",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "penalty": 0.25,
  "question": {
    "instructions": "Does `sentences[{i}]` name a harm in abstract or clinical terms, such as 'medical conditions', 'adverse outcomes', 'food insecurity', 'housing instability', or 'disparities', instead of what a person actually goes through?",
    "criteria": {
      "true": "The harm is a category word a person would not use about their own life.",
      "false": "The harm is concrete and felt: cancer, strep throat, skipping meals, losing the apartment, working two jobs and still not making rent, or the sentence names no harm."
    }
  }
}
```

### 5.5 Says what people get

```json
{
  "id": "outcomes.says-what-people-get",
  "axis": "outcomes",
  "level": "message",
  "type": "noul",
  "weight": 2,
  "question": {
    "instructions": "Does `message` contain at least one sentence that says, in everyday terms, what a person's life would be like if the message got its way?",
    "criteria": {
      "true": "At least one sentence describes a concrete lived result, for example 'you're at your new baby's side' or 'seniors retire in dignity'.",
      "false": "Results are described only as policies, programs, rights, access, or improvements."
    }
  }
}
```

### 5.6 Holistic

```json
{
  "id": "outcomes.holistic",
  "axis": "outcomes",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "Does `message` talk about outcomes people live, or about policies and processes?",
    "criteria": [
      "Policy and process throughout: programs, bills, eligibility, funding, coverage, and people appear as categories",
      "Mostly policy language with an occasional human result",
      "Mostly lived outcomes, with some policy or process language left in",
      "Lived outcomes throughout: what people have, do, and go through, with people named as people"
    ]
  }
}
```

---

## Axis 6. Don't think of an elephant (`no-elephant`)

Do not repeat the other side's claim, even to deny it. "Anytime we say what we're NOT, we bring the very thing we hope to counter to the top of mind." Denying a claim can also make it stronger (the backfire effect); refuting a claim, if it must be done, works better unemotionally (C3 p8). The framing paper cites Lakoff's elephant and warns not to lead with a fact that conflicts with the listener's belief, and not to repeat "tax relief" style language even to oppose it (FR p5, p14). The toolkit reports a vaccination study where myth-busting left people less likely to vaccinate, and the testing guide's telephone game shows people remember the myth and forget the correction (FET p42, TEST p21). Use the toolkit's ABC instead: acknowledge the concern, bridge, communicate your own frame (FET p43).

This axis and axis 3 pull in opposite directions unless you read this one narrowly, so read it narrowly. What this axis forbids is restating the other side's claims, arguments, and coined phrases. It does not forbid saying who is causing the harm and what they are doing, which axis 3 requires you to say. "A small group of corporate landlords bought up half the rental housing and raised the rent on every unit" names a villain and repeats no claim, so it costs nothing here. "They say rent control hurts renters, but it does not" repeats a claim, so it costs a great deal. A message that simply never mentions that there is a conflict is not doing well on this axis; it is doing nothing at all, and the other axes say so.

Embrace: "We support X plan that makes childcare affordable so any working parent can have their kid in great care. Anything else falls short." "Immigrants contribute to our culture and community and we're all the better for having them here." "Immigrant Americans move here for the promise of freedom and opportunity." (C3 p8)

Replace: "This is not an adequate child care plan." "Immigrants are not 'criminal aliens'." "Being undocumented is not a crime." "No human is illegal." "The vast majority of Muslims pose no threat to our security." "[Program] doesn't discourage work." (C3 p8)

### 6.1 Negates an opposing claim

```json
{
  "id": "no-elephant.negates-claim",
  "axis": "no-elephant",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 2,
  "penalty": 0.34,
  "question": {
    "instructions": "Does `sentences[{i}]` state an opposing claim, stereotype, or accusation in order to deny it, correct it, or call it a myth?",
    "criteria": {
      "true": "The sentence repeats the thing it argues against, in a form such as 'X is not Y', 'it is a myth that', 'despite what they say', 'contrary to claims', or 'no human is illegal'.",
      "false": "The sentence states the author's own claim in its own terms without restating an opposing one."
    }
  }
}
```

### 6.2 Repeats the opponent's frame

Code prefilters with a lexicon of frame words the right owns. Jev decides whether the sentence adopts the frame or only names it.

```json
{
  "id": "no-elephant.opponent-frame",
  "axis": "no-elephant",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1.5,
  "penalty": 0.34,
  "detector": "\\b(tax relief|illegals?|illegal (immigration|immigrants?|aliens?)|criminal aliens?|amnesty|government takeover|socialized|welfare|entitlements?|handouts?|death tax|broken (immigration )?system|law and order|tough on crime|job creators|big government|open borders|defund|woke|politically correct|political correctness|pro-life|partial.birth|sanctuary cit\\w+|chain migration|anchor bab\\w+|voter fraud|election integrity|war on)\\b",
  "question": {
    "instructions": "Does `sentences[{i}]` use a phrase coined by political opponents, such as 'tax relief', 'illegal immigration', 'entitlements', or 'government takeover', as if it were a neutral description rather than quoting it to reject it?",
    "criteria": {
      "true": "The phrase is used in the author's own voice, so the opponent's framing is repeated and reinforced.",
      "false": "The phrase appears only in quotation marks or clearly attributed to the other side, or the sentence does not use the phrase in the opponent's sense."
    }
  }
}
```

### 6.3 Leads with a rebuttal

```json
{
  "id": "no-elephant.leads-with-rebuttal",
  "axis": "no-elephant",
  "level": "message",
  "type": "noul",
  "bad": true,
  "weight": 1.5,
  "question": {
    "instructions": "Do the first three sentences of `message` restate a claim, argument, or accusation an opponent has made, in order to answer it? Naming who is causing a harm, or saying what they are doing, is not restating a claim and does not count.",
    "criteria": {
      "true": "The message opens by repeating the other side's claim, argument, or accusation, whether to refute it or mock it.",
      "false": "The message opens in its own frame and its own terms. It may name an opponent and say what they are doing, as long as it does not repeat what they claim."
    }
  }
}
```

### 6.4 Share of the message spent on the opposition

```json
{
  "id": "no-elephant.share-on-opposition",
  "axis": "no-elephant",
  "level": "message",
  "type": "score",
  "bad": true,
  "weight": 1,
  "question": {
    "instructions": "How much of `message` restates what opponents claim or argue, in the opponents' own terms? Only restated claims, arguments, and coined phrases belong in this judgment. Naming who is causing a harm, or reporting what they are doing, is the message's own argument and is not a restatement.",
    "criteria": [
      "None: no claim or argument of the opposition is ever restated, though the message may still name who is causing the harm",
      "Brief: one passing restatement of an opposing claim, and the message returns at once to its own argument",
      "Substantial: a section of the message is given over to answering an opposing claim",
      "Dominant: the message is organized around the opposition's claims and spends most of its words answering them"
    ]
  }
}
```

### 6.5 Holistic

```json
{
  "id": "no-elephant.holistic",
  "axis": "no-elephant",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "Does `message` argue in its own frame and its own words, or does it restate the other side's claims and phrases and argue with them? Naming who is causing a harm, or saying what they are doing, is the message's own argument and not a restatement.",
    "criteria": [
      "Organized as a rebuttal: repeats the opponent's claims and words, and its own position exists only as a denial",
      "Mixes its own argument with repeated opponent claims and frame words",
      "Mostly its own frame with one or two slips such as an 'X is not Y' sentence or an opponent's phrase used in the author's voice",
      "Entirely its own frame and its own words: it may name who is causing the harm, but it never restates what the opposition claims"
    ]
  }
}
```

---

## Axis 7. Inclusive we (`inclusive-we`)

Control the "we". The listener should be inside the group the message speaks for, not looking at "them". Say "Americans", "Californians", "working people", "our neighbors", not "immigrants", "poor people", "minorities" as groups separate from the reader (FR p14, p15). Make it about all of us, then name the particular circumstances of communities that face barriers (C3 p9). Do not compare communities against each other and do not lead with race, historical legacy, or fairness: it triggers separate-fates and blame frames and makes white audiences tune out (FR p12, p15). Find common ground by asking people to imagine themselves in a similar position, and let allies be motivated by shared values rather than personal interest (FET p34, p36).

Embrace: "Everyone means everyone, no exceptions." "Politicians choose to do X, especially in communities of color." "No matter what you look like or where you come from." "The places that need it most." "No matter your zip code." "We're one nation and our fates are shared." (C3 p9, FR p11)

Replace: "The vulnerable." "The minority community." "Immigrants need..." "Black and brown people face..." as an opening. "Latinos are twice as likely as whites to..." (comparison between communities, FR p15)

### 7.1 The reader is inside the we

```json
{
  "id": "inclusive-we.reader-inside",
  "axis": "inclusive-we",
  "level": "message",
  "type": "noul",
  "weight": 2,
  "question": {
    "instructions": "When `message` says 'we', 'us', or 'our', or names the people it speaks for, does that group include a reader from `audience`, rather than only the organization or only a community the reader may not belong to?",
    "criteria": {
      "true": "The 'we' is people, families, neighbors, Americans, or working people, a group the reader belongs to.",
      "false": "The 'we' is the organization, its staff, its members, or a specific community the reader is asked to help from outside, or there is no 'we' at all."
    }
  }
}
```

### 7.2 Shared value before particular harm

```json
{
  "id": "inclusive-we.shared-before-particular",
  "axis": "inclusive-we",
  "level": "message",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "Where `message` describes a harm that falls on a particular community, such as a racial group, immigrants, or a neighborhood, does it first state a value or goal that applies to everyone and then name that community's particular circumstances?",
    "criteria": {
      "true": "The message goes from 'all of us' to 'especially these people', or it does not single out a community at all.",
      "false": "The message opens with or is organized around one community's harm before any shared value is stated."
    }
  }
}
```

### 7.3 Everyone language

```json
{
  "id": "inclusive-we.everyone-language",
  "axis": "inclusive-we",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "question": {
    "instructions": "Does `message` contain a phrase that explicitly includes everyone, such as 'no matter where you come from', 'no matter your zip code', 'everyone means everyone', or 'whether you live in a big city or a small town'?",
    "criteria": {
      "true": "At least one such inclusive phrase is present.",
      "false": "No such phrase is present."
    }
  }
}
```

### 7.4 Othering labels

```json
{
  "id": "inclusive-we.othering-label",
  "axis": "inclusive-we",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "penalty": 0.25,
  "question": {
    "instructions": "Does `sentences[{i}]` describe a group of people, such as immigrants, minorities, the poor, people of color, or marginalized communities, as a separate 'they' that the reader is outside of?",
    "criteria": {
      "true": "The group is spoken about as others whom the reader might help, fear, or pity, with no language that places the reader in the same boat.",
      "false": "The group is included within a shared 'we' or 'all of us', the sentence speaks in the group's own voice, or the sentence names no group."
    }
  }
}
```

### 7.5 Comparison between communities

```json
{
  "id": "inclusive-we.comparison",
  "axis": "inclusive-we",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "penalty": 0.5,
  "question": {
    "instructions": "Does `sentences[{i}]` compare one racial, ethnic, or other community's outcomes against another community's, for example 'twice as likely as white families'?",
    "criteria": {
      "true": "One community is measured against another.",
      "false": "No comparison between communities is made."
    }
  }
}
```

### 7.6 Holistic

```json
{
  "id": "inclusive-we.holistic",
  "axis": "inclusive-we",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "Would a reader from `audience` feel included in the 'we' of `message`?",
    "criteria": [
      "The reader is outside: the message is about 'them', a group the reader is asked to help, or the 'we' is only the organization",
      "The 'we' is the organization's cause and its allies, and the reader is invited to join but not assumed to belong",
      "The reader is mostly inside a broad 'we', with some passages that slip into talking about a separate group",
      "The reader is inside throughout: one shared 'we', shared fate, and particular communities named as part of that 'we', not apart from it"
    ]
  }
}
```

---

## Axis 8. Frame choice (`frame`)

Frames the sources found to work with American audiences: opportunity for all (FR p6, p10), American ingenuity and can-do (FR p11), one nation with shared fates (FR p11), diversity as strength (FR p12), prevention and the miner's canary (FR p12), family and care (C3 p4), freedom, and fairness stated as rules of the game rather than as grievance (C3 p5, FR p5). Frames the sources found to backfire: white privilege, which produced guilt and resentment (FR p12); personal responsibility, God or nature as cause, colorblindness, and separate fates, all of which let listeners blame the people harmed (FR p8, p9); historical legacy as the lead (FR p15); the triumphant individual who overcame the odds, which implies others could too (FR p9). The toolkit adds emotional register: fear and guilt demotivate, making people feel insecure demotivates, economic-benefit arguments crowd out values, and making people laugh works (FET p31). Zero-sum framing, where one group's gain is another's loss, feeds opposition (FET p20). Where Olson allows negative IF/THEN and dollar stakes (GYM p38, p41), the toolkit wins for this judge.

Embrace: "Everyone deserves a fair shot." "We can solve this. Americans always have." "We're one nation, and when one of us falls, we all do." "Being there for the people you love isn't negotiable." (FR p10, p11; C3 p7)

Replace: "If you're white, you benefit from a system built for you." "Katrina showed what happens when people don't take responsibility." "Slavery's legacy explains..." as a lead. "This will cost taxpayers $3 billion." "If we don't act, thousands will die." (FR p8, p9, p12; FET p31)

### 8.1 Dominant frame

The script maps the chosen option to a score with `scores`.

```json
{
  "id": "frame.dominant",
  "axis": "frame",
  "level": "message",
  "type": "choice",
  "weight": 2,
  "scores": {
    "opportunity for all": 1.0,
    "ingenuity and can-do": 1.0,
    "one nation, shared fate": 1.0,
    "family and care": 1.0,
    "freedom": 0.9,
    "fair rules of the game": 0.9,
    "diversity as strength": 0.8,
    "prevention": 0.7,
    "economic cost or benefit": 0.3,
    "white privilege or guilt": 0.0,
    "historical legacy": 0.2,
    "personal responsibility": 0.1,
    "fear of what happens if we lose": 0.2,
    "no clear frame": 0.3
  },
  "question": {
    "instructions": "Which frame carries the argument of `message`? Choose the one the message relies on most.",
    "criteria": {
      "opportunity for all": "Everyone should get a fair shot to make a good life.",
      "ingenuity and can-do": "Americans solve problems; we can fix this.",
      "one nation, shared fate": "What happens to one of us happens to all of us.",
      "family and care": "Being there for and providing for the people you love.",
      "freedom": "Freedom to live your life, make your choices, be safe from control.",
      "fair rules of the game": "The rules are rigged by a few and should work for everyone.",
      "diversity as strength": "Our differences make us stronger.",
      "prevention": "Fix it now for the people hit first and everyone benefits later.",
      "economic cost or benefit": "The argument rests on dollars, growth, or savings.",
      "white privilege or guilt": "White people benefit unfairly and should feel responsible.",
      "historical legacy": "Past injustice such as slavery or redlining explains the present and is the lead argument.",
      "personal responsibility": "Individuals succeed or fail by their own choices.",
      "fear of what happens if we lose": "The argument rests on a threat or a disaster to be avoided.",
      "no clear frame": "No single frame carries the argument."
    }
  }
}
```

### 8.2 Fear appeal

```json
{
  "id": "frame.fear",
  "axis": "frame",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "penalty": 0.25,
  "question": {
    "instructions": "Does `sentences[{i}]` try to move the reader mainly by fear, warning of a disaster, threat, or loss?",
    "criteria": {
      "true": "The sentence's force comes from something frightening that will happen, for example 'if we don't act, thousands will die'.",
      "false": "The sentence names a problem without relying on threat, or describes something positive, or is not persuasive in intent."
    }
  }
}
```

### 8.3 Guilt or shame appeal

```json
{
  "id": "frame.guilt",
  "axis": "frame",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "penalty": 0.34,
  "question": {
    "instructions": "Does `sentences[{i}]` try to move the reader by making them feel guilty, ashamed, or complicit?",
    "criteria": {
      "true": "The sentence blames the reader or the reader's group, or says they benefit unfairly, or that inaction makes them responsible.",
      "false": "The sentence does not assign guilt or shame to the reader."
    }
  }
}
```

### 8.4 Money as the motivator

```json
{
  "id": "frame.money-motivator",
  "axis": "frame",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 0.75,
  "penalty": 0.25,
  "detector": "(\\$|\\b(dollars?|billion|million|cost|costs|savings?|taxpayers?|economy|economic|GDP|revenue|budget)\\b)",
  "question": {
    "instructions": "Does `sentences[{i}]` argue for its position mainly on the grounds of money: cost, savings, economic growth, or return on investment?",
    "criteria": {
      "true": "The reason given for the position is financial.",
      "false": "Money appears only as a detail, as a description of what a villain took, or not at all, and the reason given is a value or a human outcome."
    }
  }
}
```

### 8.5 Blame-frame trigger

```json
{
  "id": "frame.blame-trigger",
  "axis": "frame",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "penalty": 0.34,
  "question": {
    "instructions": "Does `sentences[{i}]` invite the reader to explain a group's hardship by that group's own choices, by fate or nature, or by saying the group's fate is separate from the reader's?",
    "criteria": {
      "true": "The sentence uses the language of personal responsibility, bad choices, culture, fate, God, or nature to explain hardship, or describes a community as facing a problem that is theirs alone.",
      "false": "Hardship is explained by decisions of identifiable actors or by rules that affect everyone, or no hardship is explained."
    }
  }
}
```

### 8.6 Zero-sum trigger

```json
{
  "id": "frame.zero-sum",
  "axis": "frame",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 0.75,
  "penalty": 0.34,
  "question": {
    "instructions": "Does `sentences[{i}]` present the message's goal as one group gaining at another group's expense?",
    "criteria": {
      "true": "Helping one group is framed as taking from, costing, or ranking above another group of ordinary people, for example 'our kids should come first'.",
      "false": "The gain is framed as shared, or the only one who loses is a named villain such as a CEO or a politician, or no gain or loss is described."
    }
  }
}
```

### 8.7 Historical legacy as the lead

```json
{
  "id": "frame.legacy-lead",
  "axis": "frame",
  "level": "message",
  "type": "noul",
  "bad": true,
  "weight": 0.75,
  "question": {
    "instructions": "Does `message` open its argument with historical injustice, such as slavery, segregation, redlining, or colonization, as the explanation for the problem?",
    "criteria": {
      "true": "History is the first or main reason given.",
      "false": "History is absent, or it appears later as supporting context after a present-day value and a present-day actor."
    }
  }
}
```

### 8.8 The triumphant individual

```json
{
  "id": "frame.triumphant-individual",
  "axis": "frame",
  "level": "message",
  "type": "noul",
  "bad": true,
  "weight": 0.5,
  "question": {
    "instructions": "Does `message` tell the story of one person who overcame hardship through personal effort, as its main example?",
    "criteria": {
      "true": "The central story is an individual who beat the odds by working hard or making good choices.",
      "false": "There is no such story, or the story shows how a rule, a decision, or joining together changed things for many people."
    }
  }
}
```

### 8.9 Emotional register

```json
{
  "id": "frame.register",
  "axis": "frame",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "What is the dominant emotional register of `message`?",
    "criteria": [
      "Fear, anger, or guilt throughout: the reader is meant to feel threatened, ashamed, or under attack",
      "Mostly grievance and worry, with the good outcome mentioned but not felt",
      "Determined and grounded: the problem is real and the tone is resolved, with some warmth or pride",
      "Hopeful and confident: the reader is invited to feel pride, warmth, humor, or determination, and the problem is an obstacle to a good thing we can reach"
    ]
  }
}
```

### 8.10 Holistic

```json
{
  "id": "frame.holistic",
  "axis": "frame",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "Judge the frames `message` activates in a reader from `audience`. Frames that work: opportunity for all, ingenuity and can-do, one nation and shared fate, family and care, freedom, fair rules, diversity as strength, prevention. Frames that backfire: white privilege and guilt, personal responsibility, historical legacy as the lead, fear, cost and benefit, one group against another.",
    "criteria": [
      "Relies on a frame that backfires, or activates one even while arguing against it",
      "Names a working frame as a slogan and builds nothing on it, or mixes working frames with backfiring ones so the reader could take either away",
      "Carries the argument in a working frame with a concrete situation behind it, with minor slips such as a fear line or a dollar figure carrying an argument",
      "Carries the whole argument in working frames, each one built on a concrete situation, and avoids the ones that backfire"
    ]
  }
}
```

---

## Axis 9. Audience lexicon (`lexicon`)

Know your audience and meet people where they are (FR p12, ORG p1). Words that are second nature inside the movement, such as "structural racism", "equity", "marginalized communities", "intersectional", do not land with most Americans and some, like "white privilege" and "politically correct", trigger the other side's frame (FR p12, p13). The testing guide's first check is whether a reader can say back the main point in one sentence (TEST p13, p32). Plain words are not dumbed down: C3's samples use "make ends meet", "provide for our families", "the rules about work and wages".

Embrace: "The rules about work and wages." "Politicians choose to do X, especially in communities of color." "Someone who works hard should be able to make ends meet." (C3 p7, p9)

Replace: "Systemic inequities." "Structural racism." "Marginalized communities." "Equity." "Centering the most impacted." "Stakeholders." "Capacity building." (C3 p5, FR p12)

### 9.1 Insider jargon

```json
{
  "id": "lexicon.insider-jargon",
  "axis": "lexicon",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 2,
  "penalty": 0.25,
  "detector": "\\b(structural|systemic|institutional|intersectional\\w*|equity|equitable|inequit\\w+|marginaliz\\w+|BIPOC|Latinx|centering|center(ed)? the|lived experience|stakeholders?|capacity.building|solidarity|neoliberal\\w*|liberat\\w+|decoloniz\\w+|hegemon\\w+|praxis|disparit\\w+|underserved|underrepresented|historically excluded|folks|impacted communit\\w+|frontline communit\\w+|movement building|power building|narrative change|justice-involved|unhoused|carceral|abolition\\w*)\\b",
  "question": {
    "instructions": "Would a typical reader from `audience` find `sentences[{i}]` written in the language of activists, academics, or nonprofit staff rather than in words they use themselves?",
    "criteria": {
      "true": "The sentence relies on movement or policy vocabulary such as 'systemic', 'equity', 'marginalized', 'intersectional', 'stakeholders', or 'centering' to make its point.",
      "false": "The sentence's point is made in everyday words a neighbor would use, even if a technical term appears once and is explained."
    }
  }
}
```

### 9.2 Unexplained acronym or bill number

```json
{
  "id": "lexicon.unexplained-acronym",
  "axis": "lexicon",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 0.75,
  "penalty": 0.25,
  "detector": "\\b((?-i:[A-Z]{2,6})|[HS]\\.? ?[BR]\\.? ?\\d+|Prop(osition)? \\d+)\\b",
  "question": {
    "instructions": "Does `sentences[{i}]` use an acronym, agency name, or bill number that a typical reader from `audience` would not recognize, without saying what it is in plain words?",
    "criteria": {
      "true": "An acronym or bill number such as 'SNAP', 'HB 1234', or 'CMS' carries meaning the reader would need to look up, and the sentence does not explain it.",
      "false": "The acronym is one nearly everyone knows, such as 'USA', 'TV', or 'CEO', or the sentence explains it in plain words, or no acronym is present."
    }
  }
}
```

### 9.3 Could say it back

```json
{
  "id": "lexicon.say-it-back",
  "axis": "lexicon",
  "level": "message",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "Could a typical reader from `audience`, after one reading of `message`, say back its main point in one plain sentence?",
    "criteria": {
      "true": "The main point is stated plainly enough and prominently enough that a reader would repeat it in roughly the message's own words.",
      "false": "The reader would struggle to say what the main point is, because it is buried, abstract, or spread over several competing points."
    }
  }
}
```

### 9.4 Meets the audience where they are

```json
{
  "id": "lexicon.meets-audience",
  "axis": "lexicon",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "question": {
    "instructions": "Does `message` speak in terms that fit the concerns, experience, and vocabulary of `audience`, rather than the concerns and vocabulary of the organization writing it?",
    "criteria": {
      "true": "The examples, references, and words match what the audience knows and cares about.",
      "false": "The message assumes the audience already shares the author's vocabulary, priorities, and background knowledge."
    }
  }
}
```

### 9.5 Holistic

```json
{
  "id": "lexicon.holistic",
  "axis": "lexicon",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "How plain and how well matched to `audience` is the language of `message`?",
    "criteria": [
      "Written for insiders: movement vocabulary, policy names, and acronyms throughout, and a typical reader from the audience could not say back the point",
      "Mostly insider language with a few plain passages",
      "Mostly plain, with a few jargon words or unexplained references",
      "Plain everyday language throughout, in words the audience uses about their own lives, and the point could be said back in one sentence"
    ]
  }
}
```

---

## Axis 10. Confidence (`confidence`)

Get less modest. "Seek to", "strive to", "work to", "aim to" tell the reader you expect not to succeed. State what you do and what you will achieve (C3 p12). Olson's home stretch rule points the same way: no new hedges or contradictions once you are in the solution (GYM p54).

Embrace: "We achieve..." "We create..." "Our campaign challenges..." "Our coalition builds..." (C3 p12)

Replace: "We work to achieve..." "We strive to create..." "Our campaign seeks to challenge..." "Our coalition is dedicated to building..." (C3 p12)

### 10.1 Hedge verbs

```json
{
  "id": "confidence.hedge-verbs",
  "axis": "confidence",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 2,
  "penalty": 0.25,
  "detector": "\\b(seeks? to|seeking to|striv\\w+ to|works? to|working to|aims? to|aiming to|tr(y|ies|ying) to|hop\\w+ to|attempt\\w* to|dedicated to|committed to|endeavor\\w* to|efforts? to)\\b",
  "question": {
    "instructions": "Does `sentences[{i}]` describe what the author or the author's organization does using a hedge such as 'seeks to', 'strives to', 'works to', 'aims to', 'is committed to', or 'is dedicated to', instead of stating the action or result outright?",
    "criteria": {
      "true": "The author's own work is described as an attempt or an intention.",
      "false": "The action or result is stated outright, or the hedge refers to someone other than the author."
    }
  }
}
```

### 10.2 Hedged claims

```json
{
  "id": "confidence.hedged-claim",
  "axis": "confidence",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "penalty": 0.25,
  "detector": "\\b(may|might|could|perhaps|possibly|somewhat|arguably|in some ways|to some extent|we believe|we think|we feel|it seems|hopefully|potentially)\\b",
  "question": {
    "instructions": "Does `sentences[{i}]` weaken its own claim with qualifiers such as 'may', 'might', 'perhaps', 'we believe', or 'to some extent' where a plain statement was possible?",
    "criteria": {
      "true": "The qualifier makes the author sound unsure of their own position.",
      "false": "The qualifier is accurate and necessary, describes someone else's position, or is absent."
    }
  }
}
```

### 10.3 Speaks as if winning

```json
{
  "id": "confidence.speaks-as-winning",
  "axis": "confidence",
  "level": "message",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "Does `message` speak with the confidence of a side that expects to win, describing what it does and will achieve, rather than what it hopes, tries, or struggles to do?",
    "criteria": {
      "true": "The message states its work and its outcomes as facts and expectations.",
      "false": "The message sounds embattled, apologetic, or uncertain about its own success."
    }
  }
}
```

### 10.4 Holistic

```json
{
  "id": "confidence.holistic",
  "axis": "confidence",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "How confident does the voice of `message` sound?",
    "criteria": [
      "Apologetic or embattled: hedges, attempts, and qualifiers throughout",
      "Uneven: some plain claims mixed with 'we seek to' and 'we hope'",
      "Mostly confident with an occasional hedge",
      "Confident throughout: states what it does and what will happen, like a side that expects to win"
    ]
  }
}
```

---

## Axis 11. The ask (`ask`)

Define what success looks like and ask for a specific action. "Raising awareness" is never the end goal. Make it easy to say yes: the ask is concrete, small enough to do now, and there are no more than three asks in one message (ORG p2). Engage the heart before the head; people act on what they feel (ORG p2). The toolkit says the same from the framing side: a problem without a solution demotivates, and people are demotivated if they cannot see their own role. Offer a ladder: what you can do in one minute, three minutes, an hour, a day (FET p37). Show that change is possible and that people together can win (FET p37, C3 p19). Olson: get to the BUT quickly, and the THEREFORE should be something the reader can act on (GYM p72).

Embrace: "Sign the petition today." "Join us Saturday at 10 at the courthouse." "Call Senator X at this number and say you support paid time to care." "Chip in $5 to bail out a mother before Mother's Day." (ORG p2, C3 p19)

Replace: "Learn more." "Get involved." "Raise awareness." "Stay informed." "We need everyone to do their part." Five different asks in one email.

### 11.1 There is an ask

```json
{
  "id": "ask.has-ask",
  "axis": "ask",
  "level": "message",
  "type": "noul",
  "weight": 2,
  "question": {
    "instructions": "Does `message` ask the reader to take a specific action, such as sign, call, come, give, vote, share, or join?",
    "criteria": {
      "true": "The reader is asked to do a specific thing.",
      "false": "The message informs, argues, or describes, and asks nothing of the reader, or asks only to 'learn more' or 'stay tuned'."
    }
  }
}
```

### 11.2 How many asks

```json
{
  "id": "ask.count",
  "axis": "ask",
  "level": "message",
  "type": "choice",
  "weight": 1,
  "scores": {
    "none": 0.0,
    "one": 1.0,
    "two or three": 0.7,
    "four or more": 0.2
  },
  "question": {
    "instructions": "How many distinct actions does `message` ask the reader to take? Count different actions, not repetitions of the same ask.",
    "criteria": {
      "none": "No action is asked of the reader.",
      "one": "One action, possibly repeated.",
      "two or three": "Two or three different actions.",
      "four or more": "Four or more different actions."
    }
  }
}
```

### 11.3 The ask is specific

```json
{
  "id": "ask.specific",
  "axis": "ask",
  "level": "message",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "If `message` asks the reader to do something, is the ask specific enough that the reader knows exactly what to do, where, and when?",
    "criteria": {
      "true": "The ask names the action and gives what the reader needs to do it: a link, a place, a time, a phone number, a name, or an amount.",
      "false": "The ask is vague, such as 'get involved', 'take action', 'make your voice heard', or 'support us', or there is no ask."
    }
  }
}
```

### 11.4 The ask is easy

```json
{
  "id": "ask.easy",
  "axis": "ask",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "question": {
    "instructions": "If `message` asks the reader to do something, could the reader do it right now, in a few minutes, with what they have?",
    "criteria": {
      "true": "The first ask is small: sign, share, give a small amount, send a message, RSVP.",
      "false": "The only ask demands a large commitment such as attending a multi-day event, organizing others, or changing their life, or there is no ask."
    }
  }
}
```

### 11.5 The reader has a role

```json
{
  "id": "ask.reader-role",
  "axis": "ask",
  "level": "message",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "Does `message` show the reader how their own action matters to the outcome, so they can see their role in the change?",
    "criteria": {
      "true": "The message connects the reader's action to a result, for example 'every signature moves the council', 'when we show up, they back down'.",
      "false": "The reader is told about a problem or a solution without any part to play, or the ask is disconnected from the outcome."
    }
  }
}
```

### 11.6 Change is shown to be possible

```json
{
  "id": "ask.change-possible",
  "axis": "ask",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "question": {
    "instructions": "Does `message` show that the change it seeks can actually happen, for example by pointing to a win, momentum, growing numbers, or a decision that is about to be made?",
    "criteria": {
      "true": "The reader has a reason to believe the effort can succeed.",
      "false": "The problem is presented as vast and the solution as distant, with no evidence of progress or a real chance to win."
    }
  }
}
```

### 11.7 Heart before head

```json
{
  "id": "ask.heart-before-head",
  "axis": "ask",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "min_words": 80,
  "question": {
    "instructions": "Does `message` engage the reader's feelings, through a person, a story, a value, or a vivid scene, before it presents facts, figures, or policy details?",
    "criteria": {
      "true": "The message opens on something felt and brings facts in afterwards.",
      "false": "The message opens on facts, figures, or policy details, or never engages feeling at all."
    }
  }
}
```

### 11.8 Awareness is the only goal

```json
{
  "id": "ask.awareness-only",
  "axis": "ask",
  "level": "message",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "question": {
    "instructions": "Is the only thing `message` asks of the reader to be aware, to learn more, to stay informed, or to spread awareness?",
    "criteria": {
      "true": "Awareness, learning, or information is the sole ask.",
      "false": "The message asks for a concrete action beyond awareness, or asks nothing at all."
    }
  }
}
```

### 11.9 A way to sign up

Web pages and emails only.

```json
{
  "id": "ask.sign-up-path",
  "axis": "ask",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "media": ["web page", "email"],
  "question": {
    "instructions": "Does `message` give the reader a way to join or be contacted again, such as a sign-up, a form, an email list, a text keyword, or an RSVP?",
    "criteria": {
      "true": "A sign-up or contact path is present.",
      "false": "There is no way for the reader to join or hear from the author again."
    }
  }
}
```

### 11.10 Problem and solution balance

```json
{
  "id": "ask.problem-solution-balance",
  "axis": "ask",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "How does `message` divide its attention between the problem and what the reader can do about it?",
    "criteria": [
      "All problem: the reader is left with a bad situation and nothing to do",
      "Mostly problem, with a solution or action tacked on at the end",
      "Balanced: the problem is clear and the action and its effect get real space",
      "Solution-led: the problem is stated once and most of the message is about the change, the reader's role, and the ask"
    ]
  }
}
```

### 11.11 Holistic

```json
{
  "id": "ask.holistic",
  "axis": "ask",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "How well does `message` move a reader from `audience` to act?",
    "criteria": [
      "No ask, or the only ask is to be aware or learn more",
      "A vague ask such as 'get involved', or so many asks the reader cannot pick one",
      "One clear ask, but the reader is not shown why their action matters or that it can succeed",
      "One clear, easy, specific ask, the reader sees their role and that change is possible, and the message engages feeling before facts"
    ]
  }
}
```

---

## Axis 12. Real and felt (`real`)

Make it real: show, don't tell. A person the reader can picture, a specific scene, a story with a beginning and an end. The toolkit's story of self, us, and now: why I care, why we care, why now (FET p39, p41). Olson: specifics are what make the stakes land (GYM p40). C3's narratives are full of named people: a mother in jail on Mother's Day, Petra Falcon's own family (C3 p17, p19). Numbers without a value attached are AAA material: facts that do not move anyone (GYM p52, FR p14).

Embrace: "Whether it's routine like strep throat or scary like cancer, we all want to see a doctor without going broke." "My mother cleaned houses for thirty years so my brother and I could go to school." "This Mother's Day, a mom in Memphis will sit in a cell because she can't pay $500." (C3 p15, p17, p19)

Replace: "Approximately 2.3 million individuals are affected annually." "Studies show significant disparities in outcomes." "Our organization has a long history of advocacy."

### 12.1 A human face

```json
{
  "id": "real.human-face",
  "axis": "real",
  "level": "message",
  "type": "noul",
  "weight": 2,
  "question": {
    "instructions": "Does `message` include at least one specific person the reader could picture, named or described in concrete detail, such as their job, their family, their town, or what happened to them?",
    "criteria": {
      "true": "A specific person appears with concrete detail.",
      "false": "People appear only as groups, categories, or numbers, or not at all."
    }
  }
}
```

### 12.2 A story with a shape

```json
{
  "id": "real.story",
  "axis": "real",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "min_words": 100,
  "question": {
    "instructions": "Does `message` tell a story, meaning a sequence of events that happened to someone, with a beginning and a consequence, rather than only stating claims?",
    "criteria": {
      "true": "Something happened to someone, and the message follows what came of it.",
      "false": "The message states positions, facts, and arguments without narrating events."
    }
  }
}
```

### 12.3 Statistics without a value

```json
{
  "id": "real.stat-without-value",
  "axis": "real",
  "level": "span",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "penalty": 0.25,
  "detector": "(\\d|\\bpercent\\b|\\bmillion\\b|\\bbillion\\b|\\bthousands?\\b|\\bmillions\\b)",
  "question": {
    "instructions": "Does `sentences[{i}]` present a number or statistic without saying what it means for a person or why it matters?",
    "criteria": {
      "true": "The number stands alone as a fact, for example '2.3 million people are affected'.",
      "false": "The number is tied to a person, a value, or a consequence, for example '$500 keeps a mother from her kids', or the number is a date, a time, an address, or an amount to give."
    }
  }
}
```

### 12.4 Messenger is visible

```json
{
  "id": "real.messenger-visible",
  "axis": "real",
  "level": "message",
  "type": "noul",
  "weight": 0.75,
  "min_words": 100,
  "question": {
    "instructions": "Does the author of `message` say, in the first person, why they personally care about this, from their own life or experience?",
    "criteria": {
      "true": "The author's own stake or story is present.",
      "false": "The author is invisible, or speaks only as an institution."
    }
  }
}
```

### 12.5 Show, don't tell

```json
{
  "id": "real.show-not-tell",
  "axis": "real",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "Does `message` show its point through concrete scenes and people, or tell it through claims and abstractions?",
    "criteria": [
      "All telling: claims, statistics, and abstract nouns, nothing the reader can picture",
      "Mostly telling, with one concrete detail or example",
      "Mostly showing: specific people and scenes carry the point, with some abstract passages",
      "Showing throughout: the reader can picture the people, the place, and what happened, and the claims follow from what was shown"
    ]
  }
}
```

### 12.6 Holistic

```json
{
  "id": "real.holistic",
  "axis": "real",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "How real and felt is `message` for a reader from `audience`?",
    "criteria": [
      "Abstract and institutional: nothing in it happens to anyone the reader could picture",
      "One human detail in an otherwise abstract message",
      "Grounded in real people and events, with the messenger or the story only partly present",
      "Real people, a specific story, a visible messenger, and every number tied to what it means for someone"
    ]
  }
}
```

---

## Axis 13. Base, middle, opposition (`segments`)

One message has to do three jobs at once: engage the base, persuade the middle, and alienate the opposition. C3 is blunt about the third job. Alienating the opposition, without provoking backlash from them, is not merely acceptable, it is necessary, because messages built to please everyone leave us unable to fire up the people we need as the vanguards of change. Milquetoast messaging does not make anyone angry, but it also does not ignite anyone's passion, and it fails to tell our beliefs apart from our opponents' beliefs (C3 p10). C3 tested lines such as "every working parent should be paid enough to set their kids off for a bright future" and found they make about 15 percent of U.S. voters scurry, and to them C3 says good riddance (C3 p10). The limit is backlash: there is a difference between turning staunch detractors off and firing them up, and we do not want to energize otherwise apathetic opponents into engaging politically (C3 p10). The framing toolkit agrees and puts it as a rule of thumb: arguably, your message should in fact actively alienate your opponents in the same way their communications alienate you (FET p18). The toolkit also warns that the base must be enthused enough by the message to want to share it with others (FET p18). The testing guide states the two positive jobs as a single test: messages tend to be most effective when they PERSUADE your moveable middle and ACTIVATE your disengaged base (TEST p16), and it asks the writer to decide the intended shift in thinking before testing anything (TEST p7).

Embrace: "A greedy few rigged the game in their favor, and now too many jobs don't pay enough for our needs, let alone our wants." "Immigrant Americans moved here for the promise of freedom and opportunity in this country." "Everyone means everyone, no exceptions." (C3 p10, p13)

Replace: "We believe all stakeholders deserve a seat at the table and we look forward to working with leaders on both sides." Anything a firm opponent could sign without wincing. Also replace the opposite failure: "These people want to hurt your children and they will not stop until they are stopped", which fires up apathetic opponents instead of turning them off (C3 p10).

### 13.1 The base would act on it

The base is the reader who already shares the messenger's worldview. The question is not whether they agree, it is whether the message gives them something they want to repeat and act on.

```json
{
  "id": "segments.base",
  "axis": "segments",
  "level": "message",
  "type": "score",
  "weight": 1.5,
  "question": {
    "instructions": "Imagine a reader who already shares the author's politics and cares about this issue. What does `message` make that reader do?",
    "criteria": [
      "Ignore it: the message is dull, vague, or reads like an institutional statement, and the reader scrolls past",
      "Nod along: the reader agrees with it but feels nothing and says nothing about it afterwards",
      "Repeat it: the reader wants to say a line of it out loud to someone else, or share it",
      "Act on it: the reader feels called on by name and would sign, call, show up, or give because of it"
    ]
  }
}
```

### 13.2 The middle would move

The moveable middle holds more than one frame about the issue and can be pushed either way (FET p18). The failure to watch for is pushing them away, which is worse than leaving them cold.

```json
{
  "id": "segments.middle",
  "axis": "segments",
  "level": "message",
  "type": "score",
  "weight": 1.5,
  "question": {
    "instructions": "Imagine a reader from `audience` who has no settled view on this issue and could be persuaded either way. What does `message` do to that reader?",
    "criteria": [
      "Pushes them away: the message insults them, blames them, assumes they already agree, or uses language that marks the author as not for people like them",
      "Leaves them cold: the message is understandable but gives them no reason to care and no shared ground to stand on",
      "Makes them consider it: the message starts from something they already believe and gives them one reason to think again",
      "Moves them: the message starts from a value they hold, shows them who is harmed and who is responsible, and leaves them wanting the outcome it asks for"
    ]
  }
}
```

### 13.3 What the opposition does

A firm opponent who shrugs and moves on is the best outcome. An opponent who is provoked into acting against the message is the worst, worse than an opponent who agrees, because backlash energizes people who were otherwise apathetic (C3 p10). The script maps the chosen option to a score with `scores`.

```json
{
  "id": "segments.opposition",
  "axis": "segments",
  "level": "message",
  "type": "choice",
  "weight": 1,
  "scores": {
    "agrees with it": 0.2,
    "ignores it": 0.6,
    "repelled and moves on": 1.0,
    "provoked to act against it": 0.1
  },
  "question": {
    "instructions": "Imagine a reader who firmly opposes the author's politics on this issue. What is that reader's most likely reaction to `message`?",
    "criteria": {
      "agrees with it": "The message is so broadly worded that the opponent finds nothing to disagree with and could endorse it.",
      "ignores it": "The opponent sees nothing that concerns them and pays the message no attention.",
      "repelled and moves on": "The opponent dislikes what the message stands for, feels it is not speaking to them, and goes away without doing anything about it.",
      "provoked to act against it": "The message insults, threatens, or mocks the opponent in a way that would make them argue back, complain, organize, or turn out to vote against it."
    }
  }
}
```

### 13.4 Milquetoast

The direct test for a message written to offend nobody.

```json
{
  "id": "segments.milquetoast",
  "axis": "segments",
  "level": "message",
  "type": "noul",
  "bad": true,
  "weight": 1,
  "question": {
    "instructions": "Could someone who firmly opposes the author's politics on this issue sign their own name to `message` exactly as written, without changing a word?",
    "criteria": {
      "true": "The message is worded so that an opponent could put their name on it, because it names no villain, takes no side, and says only things everyone claims to agree with.",
      "false": "The message says at least one thing an opponent would refuse to sign, such as naming who is responsible for the harm or stating a contested value outright."
    }
  }
}
```

### 13.5 Holistic

```json
{
  "id": "segments.holistic",
  "axis": "segments",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "How well does `message` do all three jobs at once: activate the base, persuade the middle, and turn the opposition off without firing it up?",
    "criteria": [
      "Does none of the three: it bores the base, says nothing to the middle, and either pleases opponents or enrages them",
      "Does one of the three: usually it rallies the base while pushing the middle away, or it reassures the middle while saying nothing the base wants to repeat",
      "Does two of the three well, with the third weak, for example strong for base and middle but so sharp it would provoke opponents into acting",
      "Gives the base a line to repeat and an action to take, starts the middle from a value they hold, and leaves firm opponents cold rather than provoked"
    ]
  }
}
```

---

## Axis 14. Stickiness (`stickiness`)

A message is only worth what survives being retold. The testing guide has a method for this called the telephone game: pass a message from person to person and see how it comes out at the end, then look at what is forgotten and what gets transformed or twisted (TEST p19). The same guide warns about the opposite case, where the thing that survives is the wrong thing: the practice of myth-busting is not effective because people just end up remembering the myth (TEST p21), and axis 6 already penalizes messages built that way. The guide's own interview script contains the single best test question available, "can you summarise this message back at me in just one sentence?" (TEST p32, and see the survey guidance on p13). Olson says the same from the writing side. The message needs one singular narrative, because a second problem thread dilutes and confuses (GYM p30 to p31), and what people keep from a story is not the story, it is a single moment: you remember Marlon Brando saying "I'm going to make him an offer he can't refuse" (GYM p57). C3's messages are built around lines made to be repeated: "Everyone means everyone, no exceptions" and "Being there for those you love isn't negotiable" (C3 p6, p9, p13).

This axis scores the card Claude wrote, not the message directly. Three of the rules read `card.summary`, the one-sentence retelling of the message, and ask whether the value, the ask, and the villain are still in it. That is the telephone game run once, in code.

Embrace: "Everyone means everyone, no exceptions." "Being there for those you love isn't negotiable." "Health care isn't negotiable." (C3 p6, p13, p14)

Replace: "Our comprehensive approach addresses the root causes of inequity across multiple interlocking systems." A message with three problems in it, none of which is the one the reader will remember. A message whose most memorable line is the opponent's claim being corrected (TEST p21).

### 14.1 The summary carries the value

```json
{
  "id": "stickiness.summary-value",
  "axis": "stickiness",
  "level": "card",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "Does `card.summary`, which is what a reader would say if asked to retell `message` in one sentence, still contain the shared value the message stands for?",
    "criteria": {
      "true": "The one-sentence retelling names or clearly implies a value such as family, fairness, freedom, dignity, safety, or opportunity.",
      "false": "The one-sentence retelling holds only a problem, a policy, a statistic, or the name of an organization, and the value has dropped out."
    }
  }
}
```

### 14.2 The summary carries the ask

```json
{
  "id": "stickiness.summary-ask",
  "axis": "stickiness",
  "level": "card",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "Does `card.summary`, which is what a reader would say if asked to retell `message` in one sentence, still contain the action the message asks for?",
    "criteria": {
      "true": "The one-sentence retelling says what the reader or the movement is being asked to do, for example sign, call, show up, vote, or give.",
      "false": "The one-sentence retelling describes a situation or an opinion only, and the action has dropped out."
    }
  }
}
```

### 14.3 The summary carries the villain

A message with no villain at all fails this rule, and axis 3 reports the same fault at its source.

```json
{
  "id": "stickiness.summary-villain",
  "axis": "stickiness",
  "level": "card",
  "type": "noul",
  "weight": 1,
  "question": {
    "instructions": "Does `card.summary`, which is what a reader would say if asked to retell `message` in one sentence, still name who or what is causing the problem?",
    "criteria": {
      "true": "The one-sentence retelling names a person, group, industry, or deliberate choice that is doing the harm.",
      "false": "The one-sentence retelling treats the problem as something that simply happens, with nobody and nothing responsible, or names no problem at all."
    }
  }
}
```

### 14.4 A line worth repeating

```json
{
  "id": "stickiness.repeatable-line",
  "axis": "stickiness",
  "level": "message",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "Does `message` contain at least one short line, of roughly ten words or fewer, that a reader could repeat word for word to a friend without having read the rest?",
    "criteria": {
      "true": "One line is short, plain, and complete on its own, for example 'Everyone means everyone, no exceptions' or 'Being there for those you love isn't negotiable'.",
      "false": "Every sentence depends on the sentences around it, or the quotable lines are too long, too abstract, or full of jargon to be repeated from memory."
    }
  }
}
```

### 14.5 One idea

```json
{
  "id": "stickiness.single-idea",
  "axis": "stickiness",
  "level": "message",
  "type": "noul",
  "weight": 1,
  "question": {
    "instructions": "Would two different readers of `message` name the same single idea as the point of it?",
    "criteria": {
      "true": "One idea runs through the whole message and everything else in it serves that idea.",
      "false": "The message carries two or more ideas of similar size, so different readers would come away with different points."
    }
  }
}
```

### 14.6 Holistic

```json
{
  "id": "stickiness.holistic",
  "axis": "stickiness",
  "level": "message",
  "type": "score",
  "weight": 1,
  "question": {
    "instructions": "A reader from `audience` reads `message` today and tells a friend about it tomorrow with nothing in front of them. How much of it survives?",
    "criteria": [
      "Nothing survives, or the reader remembers only that it was about a topic and cannot say what it wanted",
      "The topic and the feeling survive, but not the value, the villain, or the ask",
      "The value and the problem survive, and the reader can say roughly what was wanted, without the words of the message",
      "The reader repeats a line of it almost word for word, and the value, who is responsible, and what to do all come with it"
    ]
  }
}
```

---

## Series (`series`)

Some inputs are more than one message. A file split on lines of `---` is an ordered sequence, such as an email series or a set of posts in the order they went out. A crawled site is a set of pages judged against the homepage. Either way, the messages have to agree with each other. Olson's test for a team is that everyone should be able to write the same ABT for the work, and if they cannot, the team has a messaging problem, not a writing problem (GYM p75). The organizing principles add the other half: follow up, because polite but persistent follow-up is the difference between "yes, I'll make that call" and actually making the call (ORG p2). The framing toolkit turns that into a ladder of asks, from what someone can do in one minute to what they can do in a day (FET p37), which means a later message should ask for more than an earlier one, not the same thing again.

Series rules are `pair` level. For a sequence, the state is `{"earlier": <card>, "later": <card>}` for each adjacent pair of messages. For a site, the homepage card goes in as `earlier` and each other page's card goes in as `later`, so the same rules serve both shapes and no question text has to change. The findings file still labels the two sides of a site pair `anchor` and `other`, so that a reader can tell a site comparison from a sequence comparison. The two rules that depend on order, `series.ask-escalates` and `series.follow-up`, carry `"media": ["sequence"]` so the script skips them for sites, where the pages have no order.

One series rule needs no Jev call. `series.one-ask-per-message` is computed in code from each message's `ask.count` choice: the series scores 1.0 when no message in it asks for more than one action, 0.6 when some message asks for two or three, and 0.2 when any message asks for four or more. It lands in the findings file under `series.one_ask_per_message`, as a `score` field with the per-message counts beside it, and like the pair rules it is never blended into a message's `overall`.

The series score is the weighted mean of the pair rules, reported beside the fourteen axes. It is not blended into `overall`, because a weak pair should not lower the score of a message that is good on its own.

Embrace: an email series where every message stands on the same value, blames the same actor, and asks for one thing that is bigger than the last thing: reply to this email, then sign, then come on Saturday.

Replace: a site whose homepage is about freedom and whose action page is about budget shortfalls. A three-email series that asks for a petition signature three times in the same words.

### S.1 The same value

```json
{
  "id": "series.same-value",
  "axis": "series",
  "level": "pair",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "Do `earlier.core_value` and `later.core_value` state the same underlying value, allowing for different wording?",
    "criteria": {
      "true": "Both messages stand on the same value, such as family in one and providing for the people you love in the other.",
      "false": "The two messages stand on different values, for example fairness in one and public safety in the other, so a reader who saw both would not know what the author stands for."
    }
  }
}
```

### S.2 The same villain

```json
{
  "id": "series.same-villain",
  "axis": "series",
  "level": "pair",
  "type": "noul",
  "weight": 1,
  "question": {
    "instructions": "Do `earlier.villain` and `later.villain` name the same person, group, industry, or deliberate choice as the cause of the problem?",
    "criteria": {
      "true": "Both messages blame the same actor, allowing for different wording such as 'drug companies' and 'the pharmaceutical industry'.",
      "false": "The two messages blame different actors, or one names an actor and the other treats the problem as nobody's fault."
    }
  }
}
```

### S.3 The same hero

```json
{
  "id": "series.same-hero",
  "axis": "series",
  "level": "pair",
  "type": "noul",
  "weight": 1,
  "question": {
    "instructions": "Do `earlier.hero` and `later.hero` cast the same people as the ones who can fix the problem?",
    "criteria": {
      "true": "Both messages give the same people the power to act, for example ordinary people together in both, or the same officials in both.",
      "false": "One message says ordinary people can fix this and the other says the organization or an official will fix it for them."
    }
  }
}
```

### S.4 The same ABT

```json
{
  "id": "series.same-abt",
  "axis": "series",
  "level": "pair",
  "type": "noul",
  "weight": 1.5,
  "question": {
    "instructions": "Do `earlier.abt` and `later.abt` tell the same story, meaning the same setup, the same one problem, and the same direction of solution?",
    "criteria": {
      "true": "A reader who saw both messages would describe one story told twice, with different detail or a different stage of it.",
      "false": "The two messages set up different situations, name different problems, or point at different solutions, so a reader would describe two separate campaigns."
    }
  }
}
```

### S.5 The ask gets bigger

```json
{
  "id": "series.ask-escalates",
  "axis": "series",
  "level": "pair",
  "type": "noul",
  "weight": 1,
  "media": ["sequence"],
  "question": {
    "instructions": "Does `later.ask` require more time, effort, or commitment from the reader than `earlier.ask`?",
    "criteria": {
      "true": "The later ask is a step up, for example signing a petition first and then coming to an event, or giving once and then giving monthly.",
      "false": "The later ask is the same size as the earlier one, is the same action repeated, or asks for less."
    }
  }
}
```

### S.6 The later message follows up

```json
{
  "id": "series.follow-up",
  "axis": "series",
  "level": "pair",
  "type": "noul",
  "weight": 1,
  "media": ["sequence"],
  "question": {
    "instructions": "Do `later.abt.and` and `later.summary` refer back to `earlier.ask`, so that a reader who saw both messages would understand them as one conversation?",
    "criteria": {
      "true": "The later message opens on what came of the earlier ask, or on the reader's response to it, for example 'more than 800 neighbors already signed' after an earlier ask to sign.",
      "false": "The later message sets its own scene from the start, with no mention of the earlier ask or of what came of it."
    }
  }
}
```

---

## What the judge does not measure

The judge scores how a message is built, not whether it should be sent. Four things are outside it on purpose.

Truth. The judge never checks whether a claim in the message is accurate. A well-built message full of false statements scores well here. Check the facts yourself.

Policy merit. The judge takes the position in the message as given and scores the argument for it. It has no view on whether the policy is good.

Anything that is not words. Images, video, layout, typography, the photograph at the top of the page, the voice in the ad, and the design of the sign-up form all change how a message lands, and none of them reach Jev.

Anything that needs counting inside the model. Jev judges, it does not count. Word counts, sentence counts, how many times a phrase appears, how long the message is, and the share of it spent on one subject are all computed in code before the questions go out, or not at all. When a rule seems to ask for a number, read it again: it asks Jev for a judgment and the script does the arithmetic.
