#!/usr/bin/env python3
"""Interim runner for the message:judge eval suite.

Adapted from writing-skills/draft/evals/run.py: same run_claude, parse_stream,
grading, STAND_DOWN, and --tag/--case handling. `claude plugin eval` is the
real harness and is in early access; when it lands, delete this file and use
that instead.

Two modes:

    python3 message/evals/run.py --calibrate   # Jev only, no claude, no cost
    python3 message/evals/run.py                # end-to-end cases via claude -p
    python3 message/evals/run.py --case single-email
    python3 message/evals/run.py --tag judge

`--calibrate` runs scripts/judge.py's own `fetch` and `score` against the
hand-written good/bad pairs in evals/calibration/ and checks that every good
message beats its bad twin, axis by axis. It never calls `claude -p` and
never touches an agent; it is the fast, cheap way to tell whether the
rulebook and the judge script agree with a human's sense of better and
worse before spending anything on end-to-end cases.
"""
import argparse, json, re, subprocess, sys, tempfile, os
from pathlib import Path

import yaml

EVALS = Path(__file__).resolve().parent
PLUGIN = EVALS.parent          # message/
JUDGE_DIR = PLUGIN / "skills" / "judge"
JUDGE_SCRIPT = JUDGE_DIR / "scripts" / "judge.py"
CALIBRATION = EVALS / "calibration"
# `score` ends with a line like "7 requests, 25272 input tokens, about $0.0011".
COST_LINE = re.compile(r"(\d+) requests, (\d+) input tokens, about \$([\d.]+)")
JUDGE_MODEL = "claude-haiku-4-5-20251001"

# The caveman and ponytail SessionStart hooks fire in headless runs too, and
# caveman mode compresses prose, which fails a judge for the wrong reason.
STAND_DOWN = ("For this run, caveman mode and ponytail mode are off. "
              "Write normal, full English prose.")


def split_front_matter(path):
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}, text
    _, fm, body = text.split("---\n", 2)
    return yaml.safe_load(fm) or {}, body.lstrip("\n")


def run_claude(prompt, cwd, allowed_tools, stream=False, plugin=True, model=None):
    # The prompt goes FIRST. --allowedTools and --plugin-dir are variadic, so
    # anything positional after them gets swallowed and the run dies with
    # "Input must be provided either through stdin or as a prompt argument".
    cmd = ["claude", "-p", prompt, "--append-system-prompt", STAND_DOWN]
    if model:
        cmd += ["--model", model]
    if plugin:
        cmd += ["--plugin-dir", str(PLUGIN)]
    if allowed_tools:
        cmd += ["--allowedTools", ",".join(allowed_tools)]
    if stream:
        cmd += ["--output-format", "stream-json", "--verbose"]
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900)
    return proc.stdout


def parse_stream(raw):
    """Return (last_assistant_text, [tool_call_json_strings])."""
    last, tools = "", []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result" and ev.get("result"):
            last = ev["result"]
        for block in (ev.get("message") or {}).get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools.append(json.dumps(block))
            elif isinstance(block, dict) and block.get("type") == "text" and not last:
                last = block["text"]
    return last, tools


def read_target(spec, workdir, last_message):
    if not spec or spec == "last_message":
        return last_message
    if isinstance(spec, dict) and spec.get("source") == "file":
        f = Path(workdir) / spec["path"]
        return f.read_text() if f.exists() else f"({spec['path']} was not created)"
    return last_message


def grade_tool_used(g, tools):
    pat = re.compile(g["input_match"]) if g.get("input_match") else None
    hits = [t for t in tools
            if json.loads(t).get("name") == g["tool"] and (not pat or pat.search(t))]
    lo, hi = g.get("min", 1), g.get("max")
    ok = len(hits) >= lo and (hi is None or len(hits) <= hi)
    return ok, f"{len(hits)} matching call(s), wanted min={lo} max={hi}"


def grade_regex(g, text):
    hits = re.findall(g["pattern"], text, re.M if "m" in (g.get("flags") or "") else 0)
    want = g.get("match", "contains")
    ok = (len(hits) == 0) if want == "not_contains" else (len(hits) > 0)
    return ok, f"{len(hits)} match(es), rule={want}"


def read_verdict(out):
    """Last line that is a bare verdict, ignoring markdown emphasis.

    Judges write `**PASS**` about as often as `PASS`, and an exact-string
    match would score every one of those as a FAIL.
    """
    for line in reversed(out.strip().splitlines()):
        bare = line.strip().strip("*_`#. ").upper()
        if bare in ("PASS", "FAIL"):
            return bare
    return "FAIL"


def grade_llm(g, rubric, artifact, workdir, log_name=None):
    if g["type"] == "baseline":
        base = (EVALS / g["baseline_file"]).read_text()
        artifact = f"# BASELINE (before)\n\n{base}\n\n# PRODUCED (after)\n\n{artifact}"
    prompt = (f"{rubric}\n\n--- ARTIFACT UNDER JUDGEMENT ---\n\n{artifact}\n\n"
              "--- END ---\n\nWork through the rubric's questions, then end your reply "
              "with a final line that is exactly PASS or exactly FAIL.")
    # A single judge sample is unstable. The native harness votes 2 of 3, so
    # this does too.
    votes = []
    for _ in range(3):
        out = run_claude(prompt, workdir, None, plugin=False, model=JUDGE_MODEL)
        verdict = read_verdict(out)
        votes.append(verdict)
        if log_name:
            (Path(workdir) / f"_judge-{log_name}-{len(votes)}.txt").write_text(out)
        if votes.count("PASS") == 2 or votes.count("FAIL") == 2:
            break
    passed = votes.count("PASS") > votes.count("FAIL")
    return passed, f"votes {'/'.join(votes)}"


def score_case(case_dir, tags):
    meta, prompt = split_front_matter(case_dir / "prompt.md")
    if tags and not (set(tags) & set(meta.get("tags", []))):
        return None
    cfg = {}
    if (case_dir / "case.yaml").exists():
        cfg = yaml.safe_load((case_dir / "case.yaml").read_text()) or {}

    work = tempfile.mkdtemp(prefix=f"eval-{case_dir.name}-")
    scaffold = (cfg.get("context") or {}).get("scaffold_script")
    if scaffold:
        subprocess.run(scaffold, shell=True, cwd=work, check=True,
                       env={**os.environ, "EVAL_FIXTURES": str(EVALS / "fixtures")})

    raw = run_claude(prompt, work, meta.get("allowed_tools"), stream=True)
    last, tools = parse_stream(raw)
    (Path(work) / "_transcript.jsonl").write_text(raw)
    (Path(work) / "_last_message.txt").write_text(last)

    results = []
    for gf in sorted((case_dir / "graders").glob("*.md")):
        g, rubric = split_front_matter(gf)
        if g["type"] == "tool_used":
            ok, note = grade_tool_used(g, tools)
        elif g["type"] == "regex":
            ok, note = grade_regex(g, read_target(g.get("target"), work, last))
        else:
            target = g.get("focus") or {"source": "file", "path": "post.md"}
            ok, note = grade_llm(g, rubric, read_target(target, work, last), work, gf.stem)
        results.append((gf.stem, ok, note))
    return case_dir.name, results, work


# ---------------------------------------------------------------------------
# --calibrate: Jev only, no claude, no agent runs.


def run_judge(*args, timeout=300):
    cmd = ["uv", "run", "scripts/judge.py", *args]
    return subprocess.run(cmd, cwd=JUDGE_DIR, capture_output=True, text=True, timeout=timeout)


def axis_averages(findings):
    """Mean overall score and mean per-axis score, across every message in
    the findings file. A single message averages with itself; a sequence's
    three messages average across all three, which is the right comparison
    for the drip pair since both its good and bad sides are also three
    messages."""
    messages = (findings or {}).get("messages") or {}
    overalls = [m["overall"] for m in messages.values() if "overall" in m]
    overall = sum(overalls) / len(overalls) if overalls else None
    axis_scores = {}
    for m in messages.values():
        for axis, ax in (m.get("axes") or {}).items():
            if isinstance(ax, dict) and "score" in ax:
                axis_scores.setdefault(axis, []).append(ax["score"])
    axes = {a: sum(v) / len(v) for a, v in axis_scores.items()}
    series = ((findings or {}).get("series") or {}).get("score")
    return overall, axes, series


SPEND = {"requests": 0, "input_tokens": 0, "dollars": 0.0}


def score_pair(name, sequence, spend=SPEND):
    """Fetch and score both halves of one calibration pair. Returns
    (good, bad), each of them (overall, axes, series score), or None if
    either half could not be scored, printing why."""
    work = Path(tempfile.mkdtemp(prefix=f"eval-calib-{name}-"))
    result = {}
    for suffix in ("good", "bad"):
        msg_path = CALIBRATION / f"{name}-{suffix}.md"
        cards_path = CALIBRATION / f"{name}-{suffix}.cards.json"
        if not msg_path.exists() or not cards_path.exists():
            print(f"  BAD  {name}-{suffix}: missing {msg_path.name} or {cards_path.name}")
            return None

        messages_out = work / f"{name}-{suffix}-messages.json"
        fetch_args = ["fetch", str(msg_path), "--out", str(messages_out)]
        if sequence:
            fetch_args.append("--sequence")
        proc = run_judge(*fetch_args)
        if proc.returncode != 0:
            print(f"  BAD  {name}-{suffix}: fetch failed\n{proc.stderr.strip()[-2000:]}")
            return None

        findings_out = work / f"{name}-{suffix}-findings.json"
        proc = run_judge("score", str(messages_out), str(cards_path),
                          "--out", str(findings_out))
        if proc.returncode != 0:
            print(f"  BAD  {name}-{suffix}: score failed\n{proc.stderr.strip()[-2000:]}")
            return None

        hit = COST_LINE.search(proc.stdout)
        if hit:
            spend["requests"] += int(hit.group(1))
            spend["input_tokens"] += int(hit.group(2))
            spend["dollars"] += float(hit.group(3))

        result[suffix] = axis_averages(json.loads(findings_out.read_text()))
    return result["good"], result["bad"]


def print_pair_table(name, good, bad):
    good_overall, good_axes, good_series = good
    bad_overall, bad_axes, bad_series = bad
    print(f"\n{name}")
    axes = sorted(set(good_axes) | set(bad_axes))
    bad_axis_names = []
    for axis in axes:
        g, b = good_axes.get(axis), bad_axes.get(axis)
        if g is None or b is None:
            print(f"    {axis:<16} good={'n/a' if g is None else f'{g:.2f}'} "
                  f"bad={'n/a' if b is None else f'{b:.2f}'}")
            continue
        delta = g - b
        flag = "BAD " if delta <= 0 else "ok  "
        if delta <= 0:
            bad_axis_names.append(axis)
        print(f"  {flag} {axis:<16} good={g:.2f} bad={b:.2f} delta={delta:+.2f}")
    if good_overall is None or bad_overall is None:
        print("    overall: could not compute (no messages with an 'overall' score)")
        return False, bad_axis_names
    # The series score sits beside the axes and is not blended into the
    # overall, so it gets its own row rather than a column in the table.
    if good_series is not None and bad_series is not None:
        sdelta = good_series - bad_series
        if sdelta <= 0:
            bad_axis_names.append("series")
        print(f"  {'BAD ' if sdelta <= 0 else 'ok  '} {'series':<16} "
              f"good={good_series:.2f} bad={bad_series:.2f} delta={sdelta:+.2f}")
    delta = good_overall - bad_overall
    ok = delta > 0
    print(f"  {'ok  ' if ok else 'BAD '} overall good={good_overall:.2f} "
          f"bad={bad_overall:.2f} delta={delta:+.2f}")
    return ok, bad_axis_names


def calibrate():
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("TYPESAFE_API_KEY is not set in this shell; scripts/judge.py needs it. "
              "Source your .env and re-run.")
        return 2
    if not JUDGE_SCRIPT.exists():
        print(f"scripts/judge.py does not exist yet at {JUDGE_SCRIPT}.")
        print("It is being written in parallel. This runner is ready; re-run "
              "`python3 message/evals/run.py --calibrate` once it lands.")
        return 2

    pairs = [
        ("equality-texas", False),
        ("petra-falcon", False),
        ("bail-memphis", False),
        ("drip", True),
    ]
    allok = True
    all_bad_axes = set()
    ran_any = False
    for name, sequence in pairs:
        scored = score_pair(name, sequence)
        if scored is None:
            allok = False
            continue
        ran_any = True
        ok, bad_axis_names = print_pair_table(name, *scored)
        allok &= ok
        all_bad_axes.update(bad_axis_names)

    if not ran_any:
        print("\ncalibration: no pair could be scored")
        return 2

    print()
    print(f"jev: {SPEND['requests']} requests, {SPEND['input_tokens']} input tokens, "
          f"about ${SPEND['dollars']:.4f}")
    if all_bad_axes:
        print(f"axes where a bad example scored higher than its good twin, in at "
              f"least one pair: {', '.join(sorted(all_bad_axes))}")
    print("calibration:", "good beats bad on every pair" if allok else "A PAIR REGRESSED")
    return 0 if allok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--case", default=None)
    args = ap.parse_args()

    if args.calibrate:
        sys.exit(calibrate())

    cases = sorted(d for d in EVALS.iterdir()
                   if (d / "prompt.md").exists()
                   and (not args.case or d.name == args.case))
    failed = 0
    for c in cases:
        out = score_case(c, args.tag)
        if not out:
            continue
        name, results, work = out
        for gname, ok, note in results:
            print(f"  {'ok  ' if ok else 'FAIL'} {name} / {gname}: {note}")
            failed += 0 if ok else 1
        print(f"       artifacts: {work}")
    print(f"\n{failed} grader failure(s)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
