# /// script
# requires-python = ">=3.11"
# dependencies = ["typesafe-sdk"]
# ///
"""Score persuasive political messages against the rulebook with Jev.

Four commands:

    uv run scripts/judge.py fetch <source> [--out messages.json]
    uv run scripts/judge.py score <messages.json> <cards.json> [--out findings.json]
    uv run scripts/judge.py verify <findings.json> <suggestions.json>
    uv run scripts/judge.py rules [--selftest]

The rulebook at references/rules.md holds every question. This file only parses
that rulebook, sends the questions to Jev, and does the rollup arithmetic.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULES_MD = HERE.parent / "references" / "rules.md"

DEFAULT_AUDIENCE = "the general American public; judge against what is broadly resonant with most Americans"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# Jev 1.13 limits from the TypeSafe docs, with room left for request overhead.
# Tokens are counted roughly as characters / 4.
REQUEST_TOKEN_BUDGET = 60000     # state plus all questions in one request
LONGEST_QUESTION_BUDGET = 30000  # state plus the single longest question
CHUNK_TOKEN_BUDGET = 28000       # a message longer than this is judged in parts
TOKENS_PER_SECOND = 250000
REQUESTS_PER_MINUTE = 1200
PRICE_PER_INPUT_TOKEN = 42 / 1e9  # 42 dollars per billion input tokens

VIOLATION_THRESHOLD = 0.5
# series.one-ask-per-message, scored in code from each message's ask.count choice.
# A message with no ask at all is not this rule's business, so it costs nothing here.
ONE_ASK_SCORES = {"one": 1.0, "two or three": 0.6, "four or more": 0.2}
DEFAULT_PENALTY = 0.25
# ponytail: calibration knob. A span rule's "penalty" means what it says on a message
# of this many sentences; a longer message has its violation count scaled down to it.
SPAN_REFERENCE_SENTENCES = 8


# ---------------------------------------------------------------- rulebook


def load_rulebook(path: Path = RULES_MD):
    """Read every fenced json block. The block with an "axes" key is the config."""
    text = path.read_text(encoding="utf-8")
    config = None
    rules: dict[str, dict] = {}
    for match in re.finditer(r"```json\n(.*?)\n```", text, re.S):
        block = match.group(1)
        line = text.count("\n", 0, match.start()) + 1
        try:
            data = json.loads(block)
        except json.JSONDecodeError as error:
            hint = re.search(r'"id"\s*:\s*"([^"]+)"', block)
            name = hint.group(1) if hint else f"the block at line {line}"
            raise SystemExit(f"rules.md: the json block for {name} is malformed: {error}")
        if "axes" in data:
            config = data["axes"]
            continue
        for field in ("id", "axis", "level", "type", "question"):
            if field not in data:
                hint = data.get("id", f"the block at line {line}")
                raise SystemExit(f"rules.md: {hint} has no {field!r} field")
        if data["type"] not in ("noul", "choice", "score"):
            raise SystemExit(f"rules.md: {data['id']} has an unknown type {data['type']!r}")
        if data["type"] == "choice" and not data.get("scores"):
            raise SystemExit(f"rules.md: the choice rule {data['id']} has no scores map")
        if data["id"] in rules:
            raise SystemExit(f"rules.md: two blocks share the id {data['id']}")
        rules[data["id"]] = data
    if config is None:
        raise SystemExit("rules.md: no axis table block with an 'axes' key")
    return config, rules


# ------------------------------------------------------------------- text


SKIP_TAGS = {"script", "style", "nav", "footer", "header", "noscript", "form", "aside", "svg"}
BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "section", "article", "blockquote", "td",
    "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "main",
}


class PageText(HTMLParser):
    """Turn a page into plain text, dropping navigation, script, style and footer."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip() + " "
        elif not self._skip:
            self.parts.append(data)


def html_to_text(body: str):
    parser = PageText()
    parser.feed(body)
    raw = "".join(parser.parts)
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in raw.split("\n")]
    text = "\n".join(line for line in lines if line)
    return text, parser.title.strip(), parser.links


ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "st", "jr", "sr", "vs", "etc", "e.g", "i.e",
    "u.s", "u.k", "a.m", "p.m", "inc", "ltd", "co", "sen", "rep", "gov", "no",
    "fig", "approx", "dept", "est", "cf", "al", "ave", "blvd",
}


def split_sentences(text: str) -> list[str]:
    """Split on . ! ? followed by space and a capital or a quote, skipping abbreviations."""
    sentences: list[str] = []
    for block in re.split(r"\n+", text):
        block = re.sub(r"[ \t]+", " ", block).strip()
        if not block:
            continue
        start = 0
        for match in re.finditer(r"([.!?]+)[\"'’”)\]]?\s+(?=[\"'“‘(\[A-Z0-9])", block):
            head = block[start:match.end(1)]
            last = re.split(r"[\s(\[\"']", head.strip())[-1].rstrip(".").lower()
            if match.group(1) == "." and (last in ABBREVIATIONS or len(last) == 1):
                continue
            piece = block[start:match.end()].strip()
            if piece:
                sentences.append(piece)
            start = match.end()
        tail = block[start:].strip()
        if tail:
            sentences.append(tail)
    return sentences


# ------------------------------------------------------------------ fetch


def http_get(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "")
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read(4_000_000).decode(charset, errors="replace")
        return response.geturl(), content_type, body


ASSET_SUFFIXES = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".css", ".js",
    ".zip", ".mp4", ".mp3", ".ico", ".xml", ".json", ".woff", ".woff2",
)


def crawl(start_url: str, depth: int, max_pages: int) -> list[dict]:
    """Breadth first over same-domain links, down to depth and up to max_pages."""
    domain = urllib.parse.urlparse(start_url).netloc
    queue = [(start_url, 0)]
    seen = {start_url}
    pages: list[dict] = []
    while queue and len(pages) < max_pages:
        url, level = queue.pop(0)
        try:
            final_url, content_type, body = http_get(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as error:
            print(f"skipped {url}: {error}", file=sys.stderr)
            continue
        if "html" not in content_type:
            continue
        text, title, links = html_to_text(body)
        if text:
            pages.append({"url": final_url, "title": title, "text": text})
        if level >= depth:
            continue
        for href in links:
            target = urllib.parse.urljoin(final_url, href.strip())
            target, _ = urllib.parse.urldefrag(target)
            parsed = urllib.parse.urlparse(target)
            if parsed.scheme not in ("http", "https") or parsed.netloc != domain:
                continue
            if parsed.path.lower().endswith(ASSET_SUFFIXES) or target in seen:
                continue
            seen.add(target)
            queue.append((target, level + 1))
    return pages


def cmd_fetch(args) -> int:
    source = args.source
    is_url = source.startswith(("http://", "https://"))
    if is_url and args.depth > 0:
        pages = crawl(source, args.depth, args.max_pages)
        kind = "site" if len(pages) > 1 else "single"
        if not pages:
            raise SystemExit(f"fetch: nothing readable at {source}")
        parts = pages
    else:
        if source == "-":
            body = sys.stdin.read()
            url, title = "", ""
        elif is_url:
            url, content_type, body = http_get(source)
            if "html" in content_type:
                body, title, _ = html_to_text(body)
            else:
                title = ""
        else:
            path = Path(source)
            if not path.is_file():
                raise SystemExit(f"fetch: no file at {path}")
            body, url, title = path.read_text(encoding="utf-8"), "", path.stem
        if source.endswith((".html", ".htm")) or body.lstrip().startswith(("<!DOCTYPE", "<html")):
            body, page_title, _ = html_to_text(body)
            title = page_title or title
        chunks = re.split(r"(?m)^\s*---\s*$", body) if args.sequence else [body]
        parts = []
        for chunk in chunks:
            chunk = chunk.strip()
            if chunk:
                parts.append({"url": url, "title": title, "text": chunk})
        if not parts:
            raise SystemExit("fetch: the source is empty")
        kind = "sequence" if args.sequence and len(parts) > 1 else "single"

    messages = []
    for index, part in enumerate(parts, start=1):
        text = part["text"]
        title = part.get("title") or text.split("\n", 1)[0][:120]
        messages.append({
            "id": f"m{index}",
            "title": title,
            "url": part.get("url", ""),
            "text": text,
            "sentences": split_sentences(text),
        })
    document = {"source": source, "kind": kind, "messages": messages}
    out = Path(args.out) if args.out else Path("messages.json")
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    words = sum(len(message["text"].split()) for message in messages)
    print(f"wrote {out}: {len(messages)} message(s), kind {kind}, {words} words")
    return 0


# -------------------------------------------------------------- jev calls


def sdk():
    try:
        import typesafe_sdk
    except ImportError as error:  # pragma: no cover
        raise SystemExit(f"the typesafe-sdk package is not available: {error}")
    return typesafe_sdk


def make_client():
    if not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY is not set in this shell.")
    module = sdk()
    model = os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest")
    retry = module.RetryPolicy(max_retries=5, backoff_max=8.0, timeout=180.0)
    return module.TypeSafeClient(model=model, retry=retry)


def est_tokens(value) -> int:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    return max(1, len(value) // 4)


def build_question(rule: dict, index: int | None = None):
    module = sdk()
    question = rule["question"]
    instructions = question["instructions"]
    if index is not None:
        instructions = instructions.replace("{i}", str(index))
    criteria = question.get("criteria")
    if rule["type"] == "noul":
        if criteria:
            return module.Noul(instructions=instructions, criteria=criteria)
        return module.Noul(instructions=instructions)
    if rule["type"] == "choice":
        return module.Choice(instructions=instructions, criteria=criteria)
    return module.Score(instructions=instructions, criteria=criteria)


def question_tokens(question) -> int:
    dump = getattr(question, "model_dump", None)
    return est_tokens(dump() if dump else str(question))


_SENT: list[tuple[float, int]] = []


def pace(tokens: int) -> None:
    """Keep under 250k tokens a second and 1200 requests a minute."""
    while True:
        now = time.monotonic()
        _SENT[:] = [entry for entry in _SENT if now - entry[0] < 60]
        in_second = sum(count for stamp, count in _SENT if now - stamp < 1)
        if in_second + tokens > TOKENS_PER_SECOND:
            time.sleep(0.2)
            continue
        if len(_SENT) >= REQUESTS_PER_MINUTE:
            time.sleep(60 - (now - _SENT[0][0]) + 0.1)
            continue
        _SENT.append((now, tokens))
        return


def raw_answer(result, qid: str, kind: str):
    try:
        if kind == "noul":
            answer = result.nouls[qid]
            return {"type": "noul", "noul": answer.noul}
        if kind == "choice":
            answer = result.choices[qid]
            return {
                "type": "choice",
                "choice": answer.choice,
                "probabilities": dict(answer.probabilities),
                "confidence": answer.confidence,
            }
        answer = result.scores[qid]
        return {
            "type": "score",
            "score": answer.score,
            "probabilities": dict(answer.probabilities),
            "legend": {str(key): value for key, value in dict(answer.legend).items()},
            "confidence": answer.confidence,
        }
    except (KeyError, AttributeError):
        return None


def ask(client, state, questions: dict, kinds: dict, errors: list, tally: dict, label: str) -> dict:
    """One System One request. Errors are recorded, never raised."""
    pace(est_tokens(state) + sum(question_tokens(question) for question in questions.values()))
    try:
        result = client.system_one(state, questions)
    except Exception as error:  # the SDK already retries 429 and 529
        errors.append({
            "where": label,
            "questions": sorted(questions),
            "error": f"{type(error).__name__}: {error}",
        })
        return {}
    tally["requests"] += 1
    usage = getattr(result, "usage", None)
    tally["input_tokens"] += getattr(usage, "input_tokens", None) or 0
    tally["output_tokens"] += getattr(usage, "output_tokens", None) or 0
    request_id = getattr(result, "request_id", None)
    answers = {}
    for qid in questions:
        raw = raw_answer(result, qid, kinds[qid])
        if raw is None:
            errors.append({"where": label, "questions": [qid], "error": "no answer came back for this question"})
            continue
        raw["request_id"] = request_id
        answers[qid] = raw
    return answers


def ask_batched(client, state, questions: dict, kinds: dict, errors: list, tally: dict, label: str) -> dict:
    """Pack as many questions about one state into each request as the budgets allow."""
    state_tokens = est_tokens(state)
    answers: dict = {}
    batch: dict = {}
    batch_tokens = 0
    for qid, question in questions.items():
        size = question_tokens(question)
        if state_tokens + size > LONGEST_QUESTION_BUDGET:
            errors.append({"where": label, "questions": [qid], "error": "state plus question is over the 32k budget"})
            continue
        if batch and state_tokens + batch_tokens + size > REQUEST_TOKEN_BUDGET:
            answers.update(ask(client, state, batch, kinds, errors, tally, label))
            batch, batch_tokens = {}, 0
        batch[qid] = question
        batch_tokens += size
    if batch:
        answers.update(ask(client, state, batch, kinds, errors, tally, label))
    return answers


# ------------------------------------------------------------ rollup math


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def rule_pass(rule: dict, raw: dict) -> float:
    """Turn one raw Jev answer into a 0 to 1 pass score."""
    kind = raw["type"]
    if kind == "choice":
        # The scores map already says which option is good, so nothing is inverted.
        scores = rule.get("scores") or {}
        return clamp(sum(probability * scores.get(option, 0.0) for option, probability in raw["probabilities"].items()))
    if kind == "score":
        top = max(1, len(rule["question"]["criteria"]) - 1)
        value = raw["score"] / top
    else:
        value = raw["noul"]
    if rule.get("bad"):
        value = 1.0 - value
    return clamp(value)


def scoped_sentence_count(rule: dict, sentences: list) -> int:
    """How many sentences the rule is allowed to look at, before the detector runs."""
    if rule.get("scope") in ("opening", "closing"):
        return min(3, len(sentences))
    return len(sentences)


def span_pass(rule: dict, violations: list, scoped: int = 0) -> float:
    """Subtract the penalty once per violating sentence, but normalise a long
    message down to the reference length first. Without that, a long message is
    punished simply for having more sentences to trip on: any span rule floors at
    zero after four hits, so a verbatim news story loses to a short weak rewrite.
    The scaling never goes above 1.0, so no message of reference length or shorter
    is scored any harder than the plain count would score it."""
    scale = min(1.0, SPAN_REFERENCE_SENTENCES / scoped) if scoped else 1.0
    return max(0.0, 1.0 - len(violations) * rule.get("penalty", DEFAULT_PENALTY) * scale)


def weighted_mean(pairs: list[tuple[float, float]]):
    total = sum(weight for _, weight in pairs)
    if not pairs or total <= 0:
        return None
    return sum(value * weight for value, weight in pairs) / total


def roll_axis(rule_entries: list[tuple[float, float]], holistic, share: float):
    """Weighted mean of the axis rules, blended with the holistic rule."""
    mean = weighted_mean(rule_entries)
    if mean is None:
        return holistic
    if holistic is None:
        return mean
    return (1.0 - share) * mean + share * holistic


def roll_axes(entries: dict, rules: dict, config: dict) -> tuple[dict, float | None]:
    """Group rule entries by axis, blend in each holistic rule, then the overall."""
    share = config.get("holistic_share", 0.4)
    weights = config.get("weights", {})
    axes: dict[str, dict] = {}
    for rule_id, entry in entries.items():
        axis = rules[rule_id]["axis"]
        axes.setdefault(axis, {"score": None, "holistic": None, "rules": {}})["rules"][rule_id] = entry
    for axis, block in axes.items():
        parts = []
        holistic = None
        for rule_id, entry in block["rules"].items():
            if entry.get("na") or entry.get("score") is None:
                continue
            if rule_id.endswith(".holistic"):
                holistic = entry["score"]
            else:
                parts.append((entry["score"], float(rules[rule_id].get("weight", 1))))
        block["holistic"] = holistic
        block["score"] = roll_axis(parts, holistic, share)
    overall = weighted_mean([
        (block["score"], float(weights.get(axis, 1)))
        for axis, block in axes.items()
        if block["score"] is not None
    ])
    return axes, overall


# ------------------------------------------------------------------ score


def applicable(rule: dict, words: int, medium: str, kind: str):
    """Return None when the rule runs, or the reason it is not applicable."""
    minimum = rule.get("min_words")
    if minimum and words < minimum:
        return f"the message has {words} words, under this rule's minimum of {minimum}"
    media = rule.get("media")
    if media:
        if medium in media:
            return None
        if "sequence" in media and kind == "sequence":
            return None
        return f"the medium {medium!r} is not one of {media}"
    return None


def chunk_sentences(sentences: list[str]) -> list[tuple[list[int], str]]:
    """One chunk unless the message is over the per-request text budget."""
    chunks: list[tuple[list[int], str]] = []
    indices: list[int] = []
    tokens = 0
    for index, sentence in enumerate(sentences):
        size = est_tokens(sentence)
        if indices and tokens + size > CHUNK_TOKEN_BUDGET:
            chunks.append((indices, " ".join(sentences[i] for i in indices)))
            indices, tokens = [], 0
        indices.append(index)
        tokens += size
    if indices:
        chunks.append((indices, " ".join(sentences[i] for i in indices)))
    return chunks or [([], "")]


def span_indices(rule: dict, indices: list[int], sentences: list[str]):
    """Apply scope and the detector regex before spending a Jev call."""
    detector = re.compile(rule["detector"], re.I) if rule.get("detector") else None
    scope = rule.get("scope")
    kept = []
    for local, global_index in enumerate(indices):
        if scope == "opening" and global_index > 2:
            continue
        if scope == "closing" and global_index < len(sentences) - 3:
            continue
        if detector and not detector.search(sentences[global_index]):
            continue
        kept.append((local, global_index))
    return kept


def score_message(client, message: dict, card: dict, audience: str, kind: str, config: dict, rules: dict, errors: list, tally: dict) -> dict:
    text = message["text"]
    sentences = message.get("sentences") or split_sentences(text)
    words = len(text.split())
    medium = card.get("medium") or "other"
    chunks = chunk_sentences(sentences)
    label = message["id"]

    entries: dict[str, dict] = {}
    by_level: dict[str, list[dict]] = {"message": [], "card": [], "span": []}
    for rule_id, rule in rules.items():
        if rule["axis"] == "series" or rule["level"] == "pair":
            continue
        reason = applicable(rule, words, medium, kind)
        if reason is None and rule["level"] == "card" and not card:
            reason = "no card was written for this message"
        if reason is None and rule["level"] == "card":
            missing = [f for f in rule.get("requires_card", []) if not (card.get(f) or "").strip()]
            if missing:
                reason = f"the card has no {', '.join(missing)}, so this rule does not apply"
        if reason is None and rule["level"] not in by_level:
            reason = f"unsupported level {rule['level']!r}"
        if reason:
            entries[rule_id] = {"score": None, "na": True, "reason": reason}
            continue
        by_level[rule["level"]].append(rule)

    raws: dict[str, list] = {rule["id"]: [] for group in by_level.values() for rule in group}
    spans: dict[str, list] = {rule["id"]: [] for rule in by_level["span"]}

    for indices, chunk_text in chunks:
        if by_level["message"]:
            state = {"medium": medium, "audience": audience, "message": chunk_text}
            questions = {rule["id"]: build_question(rule) for rule in by_level["message"]}
            kinds = {rule["id"]: rule["type"] for rule in by_level["message"]}
            for qid, raw in ask_batched(client, state, questions, kinds, errors, tally, f"{label} message").items():
                raws[qid].append(raw)
        if by_level["card"]:
            state = {"message": chunk_text, "card": card}
            questions = {rule["id"]: build_question(rule) for rule in by_level["card"]}
            kinds = {rule["id"]: rule["type"] for rule in by_level["card"]}
            for qid, raw in ask_batched(client, state, questions, kinds, errors, tally, f"{label} card").items():
                raws[qid].append(raw)
        if by_level["span"]:
            state = {"audience": audience, "sentences": [sentences[i] for i in indices]}
            questions, kinds, where = {}, {}, {}
            for rule in by_level["span"]:
                for local, global_index in span_indices(rule, indices, sentences):
                    qid = f"{rule['id']}#{local}"
                    questions[qid] = build_question(rule, local)
                    kinds[qid] = rule["type"]
                    where[qid] = global_index
            answers = ask_batched(client, state, questions, kinds, errors, tally, f"{label} spans")
            for qid, raw in answers.items():
                rule_id = qid.rsplit("#", 1)[0]
                global_index = where[qid]
                spans[rule_id].append({
                    "sentence_index": global_index,
                    "text": sentences[global_index],
                    "probability": raw.get("noul", raw.get("score")),
                    "raw": raw,
                })

    for rule in by_level["message"] + by_level["card"]:
        rule_id = rule["id"]
        results = raws[rule_id]
        if not results:
            entries[rule_id] = {"score": None, "na": True, "reason": "no answer came back, see errors"}
            continue
        # A message split into parts is scored per part and averaged.
        scores = [rule_pass(rule, raw) for raw in results]
        entries[rule_id] = {
            "score": sum(scores) / len(scores),
            "na": False,
            "raw": results[0] if len(results) == 1 else results,
        }

    for rule in by_level["span"]:
        rule_id = rule["id"]
        results = sorted(spans[rule_id], key=lambda item: item["sentence_index"])
        # Span rules are written as violations, so a high probability is the violation.
        # A span rule without "bad" reads the other way round.
        bad = rule.get("bad", True)
        violations = [
            {"sentence_index": item["sentence_index"], "text": item["text"], "probability": item["probability"]}
            for item in results
            if ((item["probability"] or 0) >= VIOLATION_THRESHOLD) == bad
        ]
        entries[rule_id] = {
            "score": span_pass(rule, violations, scoped_sentence_count(rule, sentences)),
            "na": False,
            "sentences_judged": len(results),
            "raw": results,
            "violations": violations,
        }

    axes, overall = roll_axes(entries, rules, config)
    return {
        "medium": medium,
        "words": words,
        "title": message.get("title", ""),
        "url": message.get("url", ""),
        "text": text,
        "sentences": sentences,
        "card": card,
        "overall": overall,
        "axes": axes,
    }


def score_series(client, messages: list[dict], cards: dict, kind: str, rules: dict, findings: dict, errors: list, tally: dict) -> dict:
    """Pair rules over adjacent messages in a sequence, or each page against the homepage."""
    pair_rules = [rule for rule in rules.values() if rule["axis"] == "series" or rule["level"] == "pair"]
    pairs = []
    if kind == "sequence":
        couples = [(messages[i], messages[i + 1], "earlier", "later") for i in range(len(messages) - 1)]
    else:
        couples = [(messages[0], other, "anchor", "other") for other in messages[1:]]
    for first, second, first_key, second_key in couples:
        first_card = cards.get(first["id"], {})
        second_card = cards.get(second["id"], {})
        # Every pair rule reads `earlier` and `later`, so the state uses those names for a
        # site too. first_key and second_key only label the two sides in the findings file.
        state = {"earlier": first_card, "later": second_card}
        entries = {}
        questions, kinds = {}, {}
        for rule in pair_rules:
            reason = applicable(rule, len(second["text"].split()), second_card.get("medium") or "other", kind)
            if reason:
                entries[rule["id"]] = {"score": None, "na": True, "reason": reason}
                continue
            questions[rule["id"]] = build_question(rule)
            kinds[rule["id"]] = rule["type"]
        label = f"{first['id']}+{second['id']}"
        answers = ask_batched(client, state, questions, kinds, errors, tally, f"{label} pair") if questions else {}
        for rule in pair_rules:
            raw = answers.get(rule["id"])
            if raw is None:
                entries.setdefault(rule["id"], {"score": None, "na": True, "reason": "no answer came back, see errors"})
                continue
            entries[rule["id"]] = {"score": rule_pass(rule, raw), "na": False, "raw": raw}
        pairs.append({first_key: first["id"], second_key: second["id"], "rules": entries})

    scores = [
        (entry["score"], float(rules[rule_id].get("weight", 1)))
        for pair in pairs
        for rule_id, entry in pair["rules"].items()
        if not entry.get("na") and entry.get("score") is not None
    ]
    asks = {}
    worst = 1.0
    for message in messages:
        entry = (findings["messages"].get(message["id"], {}).get("axes", {}).get("ask", {}).get("rules", {}).get("ask.count"))
        raw = (entry or {}).get("raw") or {}
        if isinstance(raw, list):
            raw = raw[0] if raw else {}
        choice = raw.get("choice")
        asks[message["id"]] = {"count": choice, "one_ask": choice == "one", "probabilities": raw.get("probabilities")}
        worst = min(worst, ONE_ASK_SCORES.get(choice, 1.0))
    return {
        "score": weighted_mean(scores),
        "pairs": pairs,
        "one_ask_per_message": {"score": worst, "messages": asks},
    }


def slug(source: str) -> str:
    base = urllib.parse.urlparse(source).netloc if source.startswith("http") else Path(source).stem
    base = base or "message"
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", base.lower())).strip("-") or "message"


def cmd_score(args) -> int:
    document = json.loads(Path(args.messages).read_text(encoding="utf-8"))
    cards = json.loads(Path(args.cards).read_text(encoding="utf-8"))
    audience = args.audience or (Path(args.audience_file).read_text(encoding="utf-8").strip() if args.audience_file else DEFAULT_AUDIENCE)
    config, rules = load_rulebook()
    client = make_client()
    kind = document.get("kind", "single")
    messages = document["messages"]

    errors: list = []
    tally = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
    findings = {
        "source": document.get("source", ""),
        "audience": audience,
        "kind": kind,
        "model": os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest"),
        "messages": {},
        "series": {},
        "errors": errors,
        "usage": tally,
    }
    for message in messages:
        card = cards.get(message["id"], {})
        if not card:
            print(f"warning: no card for {message['id']}, card rules are skipped", file=sys.stderr)
        findings["messages"][message["id"]] = score_message(
            client, message, card, audience, kind, config, rules, errors, tally
        )
        overall = findings["messages"][message["id"]]["overall"]
        print(f"{message['id']}: overall {overall:.3f}" if overall is not None else f"{message['id']}: no score")
    if kind in ("sequence", "site") and len(messages) > 1:
        findings["series"] = score_series(client, messages, cards, kind, rules, findings, errors, tally)

    out = Path(args.out) if args.out else Path(f"judge-{slug(findings['source'] or args.messages)}.json")
    out.write_text(json.dumps(findings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cost = tally["input_tokens"] * PRICE_PER_INPUT_TOKEN
    print(f"wrote {out}")
    print(f"{tally['requests']} requests, {tally['input_tokens']} input tokens, about ${cost:.4f}")
    if errors:
        print(f"{len(errors)} request or answer errors are recorded in the findings", file=sys.stderr)
    return 0


# ----------------------------------------------------------------- verify


def raw_value(raw: dict):
    if raw["type"] == "noul":
        return raw["noul"]
    if raw["type"] == "score":
        return raw["score"]
    return raw["probabilities"].get(raw["choice"])


def before_for(rule: dict, message_entry: dict, suggestion: dict):
    """Find what the rule scored before the replacement, from the findings file."""
    entry = message_entry.get("axes", {}).get(rule["axis"], {}).get("rules", {}).get(rule["id"])
    if not entry or entry.get("na"):
        return None, None
    if rule["level"] == "span":
        index = suggestion.get("sentence_index")
        for item in entry.get("raw") or []:
            if item["sentence_index"] == index:
                return item["probability"], rule_pass(rule, item["raw"])
        return None, None
    raw = entry.get("raw")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not raw:
        return None, None
    return raw_value(raw), rule_pass(rule, raw)


def swap_in_card(card, original: str, replacement: str):
    """Put the replacement into the card as well as the message.

    A card rule judges what the card says, so re-judging it against the original
    card would return the original answer and mark every card suggestion as no
    improvement. Only exact string values are touched, at any depth.
    """
    if not original:
        return card
    if isinstance(card, str):
        return card.replace(original, replacement)
    if isinstance(card, dict):
        return {key: swap_in_card(value, original, replacement) for key, value in card.items()}
    if isinstance(card, list):
        return [swap_in_card(value, original, replacement) for value in card]
    return card


def cmd_verify(args) -> int:
    findings = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    suggestions = json.loads(Path(args.suggestions).read_text(encoding="utf-8"))
    _, rules = load_rulebook()
    client = make_client()
    audience = findings.get("audience", DEFAULT_AUDIENCE)
    errors: list = []
    tally = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
    results = []

    for suggestion in suggestions:
        rule = rules.get(suggestion.get("rule_id", ""))
        message_entry = findings["messages"].get(suggestion.get("message_id", ""))
        record = dict(suggestion)
        if rule is None or message_entry is None:
            record["error"] = "unknown rule id or message id"
            results.append(record)
            continue
        before_probability, before_score = before_for(rule, message_entry, suggestion)
        if rule["level"] == "span":
            state = {"audience": audience, "sentences": [suggestion["replacement"]]}
            question = build_question(rule, 0)
        else:
            original = suggestion.get("original") or ""
            text = message_entry["text"]
            if original and original in text:
                text = text.replace(original, suggestion["replacement"])
            elif rule["level"] == "card":
                # A card suggestion usually rewrites a card field, not a span of the
                # message, so the message stays as it was and only the card changes.
                record["note_on_substitution"] = "the original text was not found in the message, so only the card was changed"
            else:
                record["note_on_substitution"] = "the original text was not found, the replacement was judged on its own"
                text = suggestion["replacement"]
            if rule["level"] == "card":
                state = {"message": text, "card": swap_in_card(message_entry.get("card", {}), original, suggestion["replacement"])}
            else:
                state = {"medium": message_entry.get("medium", "other"), "audience": audience, "message": text}
            question = build_question(rule)
        answers = ask(client, state, {rule["id"]: question}, {rule["id"]: rule["type"]}, errors, tally, f"verify {rule['id']}")
        raw = answers.get(rule["id"])
        if raw is None:
            record["error"] = "no answer came back"
            results.append(record)
            continue
        after_probability = raw_value(raw)
        after_score = rule_pass(rule, raw)
        record.update({
            "level": rule["level"],
            "bad_rule": bool(rule.get("bad")),
            "before_probability": before_probability,
            "after_probability": after_probability,
            "before_score": before_score,
            "after_score": after_score,
            "improved": bool(before_score is not None and after_score > before_score),
            "raw": raw,
        })
        results.append(record)

    document = {"source": findings.get("source", ""), "audience": audience, "verified": results, "errors": errors, "usage": tally}
    out = Path(args.out) if args.out else Path("verified.json")
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    improved = sum(1 for record in results if record.get("improved"))
    cost = tally["input_tokens"] * PRICE_PER_INPUT_TOKEN
    print(f"wrote {out}: {improved} of {len(results)} replacements improved")
    print(f"{tally['requests']} requests, {tally['input_tokens']} input tokens, about ${cost:.4f}")
    return 0


# ------------------------------------------------------- rules and selftest


def selftest(config: dict, rules: dict) -> None:
    """Check the rollup arithmetic on made-up answers. No network."""
    good_noul = {"id": "x.good", "axis": "x", "level": "message", "type": "noul", "question": {"instructions": "?"}}
    bad_noul = dict(good_noul, id="x.bad", bad=True)
    assert abs(rule_pass(good_noul, {"type": "noul", "noul": 0.8}) - 0.8) < 1e-9
    assert abs(rule_pass(bad_noul, {"type": "noul", "noul": 0.8}) - 0.2) < 1e-9

    score_rule = {"id": "x.s", "axis": "x", "level": "message", "type": "score", "question": {"instructions": "?", "criteria": ["a", "b", "c", "d"]}}
    assert abs(rule_pass(score_rule, {"type": "score", "score": 3.0}) - 1.0) < 1e-9
    assert abs(rule_pass(score_rule, {"type": "score", "score": 1.5}) - 0.5) < 1e-9
    assert abs(rule_pass(dict(score_rule, bad=True), {"type": "score", "score": 3.0})) < 1e-9

    choice_rule = {"id": "x.c", "axis": "x", "level": "message", "type": "choice", "scores": {"one": 1.0, "two": 0.5, "three": 0.0}, "question": {"instructions": "?"}}
    raw = {"type": "choice", "choice": "one", "probabilities": {"one": 0.5, "two": 0.4, "three": 0.1}}
    assert abs(rule_pass(choice_rule, raw) - 0.7) < 1e-9

    span_rule = {"id": "x.span", "axis": "x", "level": "span", "type": "noul", "bad": True}
    assert abs(span_pass(span_rule, [1, 2], 8) - 0.5) < 1e-9
    assert span_pass(span_rule, [1, 2, 3, 4, 5], 8) == 0.0
    assert abs(span_pass(dict(span_rule, penalty=0.5), [1], 8) - 0.5) < 1e-9
    # A message shorter than the reference length is scored by the plain count.
    assert abs(span_pass(span_rule, [1, 2], 4) - 0.5) < 1e-9
    # A message four times the reference length has the same count scaled to a quarter.
    assert abs(span_pass(span_rule, [1, 2], 32) - 0.875) < 1e-9
    assert scoped_sentence_count({}, list(range(20))) == 20
    assert scoped_sentence_count({"scope": "opening"}, list(range(20))) == 3

    card = {"summary": "Rents are up.", "abt": {"and": "Rents are up.", "but": "b"}, "medium": "email"}
    swapped = swap_in_card(card, "Rents are up.", "Landlords raised the rent.")
    assert swapped["summary"] == "Landlords raised the rent."
    assert swapped["abt"]["and"] == "Landlords raised the rent." and swapped["abt"]["but"] == "b"
    assert swap_in_card(card, "", "x") is card
    assert min(ONE_ASK_SCORES.get(c, 1.0) for c in ("one", "none")) == 1.0
    assert min(ONE_ASK_SCORES.get(c, 1.0) for c in ("one", "four or more")) == 0.2

    # Axis: weighted mean 0.6*2 + 0.2*1 over weight 3 = 0.466..., blended 60/40 with a 1.0 holistic.
    axis = roll_axis([(0.6, 2.0), (0.2, 1.0)], 1.0, 0.4)
    assert abs(axis - (0.6 * (1.4 / 3.0) + 0.4 * 1.0)) < 1e-9
    assert roll_axis([], 0.75, 0.4) == 0.75
    assert abs(roll_axis([(0.5, 1.0)], None, 0.4) - 0.5) < 1e-9

    entries = {
        "values-first.opens-with-value": {"score": 1.0, "na": False},
        "values-first.holistic": {"score": 0.5, "na": False},
        "abt.has-therefore": {"score": 0.0, "na": False},
        "abt.holistic": {"score": 0.0, "na": False},
        "ask.has-ask": {"score": None, "na": True, "reason": "test"},
    }
    axes, overall = roll_axes(entries, rules, config)
    expected_values = 0.6 * 1.0 + 0.4 * 0.5
    assert abs(axes["values-first"]["score"] - expected_values) < 1e-9
    assert axes["abt"]["score"] == 0.0
    assert "ask" in axes and axes["ask"]["score"] is None
    weights = config["weights"]
    expected_overall = (expected_values * weights["values-first"]) / (weights["values-first"] + weights["abt"])
    assert abs(overall - expected_overall) < 1e-9

    assert split_sentences("Dr. King spoke. We listened! Did we?") == ["Dr. King spoke.", "We listened!", "Did we?"]
    text, title, links = html_to_text("<html><title>T</title><body><nav>Home</nav><p>Hello there.</p><a href='/x'>x</a></body></html>")
    assert text == "Hello there. x" or text.startswith("Hello there."), text
    assert title == "T" and links == ["/x"]
    print("selftest passed")


def cmd_rules(args) -> int:
    config, rules = load_rulebook()
    if args.selftest:
        selftest(config, rules)
        return 0
    print(f"{'id':40} {'axis':13} {'level':8} {'type':7} {'weight':>6}")
    print("-" * 78)
    for rule in rules.values():
        print(f"{rule['id']:40} {rule['axis']:13} {rule['level']:8} {rule['type']:7} {float(rule.get('weight', 1)):>6.2f}")
    axes: dict[str, int] = {}
    for rule in rules.values():
        axes[rule["axis"]] = axes.get(rule["axis"], 0) + 1
    print("-" * 78)
    print(f"{len(rules)} rules over {len(axes)} axes, holistic share {config.get('holistic_share')}")
    missing = [axis for axis in config.get("weights", {}) if axis not in axes]
    if missing:
        print(f"axes with a weight but no rules yet: {', '.join(missing)}")
    extra = [axis for axis in axes if axis != "series" and axis not in config.get("weights", {})]
    if extra:
        print(f"axes with rules but no weight: {', '.join(extra)}")
    return 0


# ------------------------------------------------------------------- main


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="read a file, a URL, or stdin into messages.json")
    fetch.add_argument("source", help="a local file path, a URL, or - for stdin")
    fetch.add_argument("--out", default="messages.json")
    fetch.add_argument("--depth", type=int, default=2, help="crawl depth for a URL, 0 for the one page")
    fetch.add_argument("--max-pages", type=int, default=25)
    fetch.add_argument("--sequence", action="store_true", help="split a local file on lines of ---")
    fetch.set_defaults(func=cmd_fetch)

    score = sub.add_parser("score", help="send every applicable rule question to Jev")
    score.add_argument("messages")
    score.add_argument("cards")
    score.add_argument("--audience")
    score.add_argument("--audience-file")
    score.add_argument("--out")
    score.set_defaults(func=cmd_score)

    verify = sub.add_parser("verify", help="re-judge suggested replacements")
    verify.add_argument("findings")
    verify.add_argument("suggestions")
    verify.add_argument("--out")
    verify.set_defaults(func=cmd_verify)

    rules = sub.add_parser("rules", help="print the parsed rule table")
    rules.add_argument("--selftest", action="store_true", help="check the rollup math, no network")
    rules.set_defaults(func=cmd_rules)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
