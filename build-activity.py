#!/usr/bin/env python3
"""Build activity.json for the activity panel on indigokarasu.com.

Every request is anonymous, so GitHub only ever returns public data. On top
of that, events are kept only when GitHub marks them public and the repo is
owned by indigokarasu and is public right now.

Push and pull request events no longer carry commit messages or titles, so
those are looked up separately and cached by commit/PR, which keeps each run
well inside the anonymous limit of 60 requests an hour.

Usage: build-activity.py --out public/activity.json [--cache lookups.json]
                         [--hide patterns.txt]

--hide takes a file of regular expressions, one per line. Branch names,
commit messages and titles that match any of them are left out of the feed.
"""
import argparse
import datetime
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request

USER = "indigokarasu"
API = "https://api.github.com"
MAX_EVENTS = 100
MAX_LOOKUPS = 40  # per run; the rest are filled in on later runs

HIDE = None  # compiled from --hide


class RateLimited(Exception):
    pass


def get(path):
    req = urllib.request.Request(API + path, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "indigokarasu-site",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
            raise RateLimited(path) from e
        raise


def public_repos():
    names, page = set(), 1
    while True:
        batch = get(f"/users/{USER}/repos?type=owner&per_page=100&page={page}")
        for r in batch:
            if not r.get("private") and r.get("visibility", "public") == "public":
                names.add(r["full_name"])
        if len(batch) < 100:
            return names
        page += 1


def clean(text):
    """First line of text, or None when it matches --hide."""
    line = (text or "").strip().split("\n")[0].strip()
    if not line or (HIDE and HIDE.search(line)):
        return None
    return line[:120]


class Lookups:
    def __init__(self, path):
        self.path = path
        self.budget = MAX_LOOKUPS
        self.data = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except (OSError, ValueError):
                self.data = {}

    def fetch(self, key, path, pick):
        """Cached GitHub lookup; None when unknown or out of budget."""
        if key in self.data:
            return self.data[key]
        if self.budget <= 0:
            return None
        self.budget -= 1
        try:
            value = pick(get(path))
        except RateLimited:
            self.budget = 0
            return None
        except urllib.error.HTTPError as e:
            if e.code not in (404, 409, 422):
                return None
            value = {}  # rewritten or deleted history: remember, don't retry
        except (urllib.error.URLError, TimeoutError, ValueError):
            return None
        self.data[key] = value
        return value

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f)


def branch(ref):
    return (ref or "").removeprefix("refs/heads/").removeprefix("refs/tags/")


def fmt_push(e, repo, look):
    p = e.get("payload") or {}
    head, before, br = p.get("head"), p.get("before"), clean(branch(p.get("ref")))
    info = None
    if head and before and before.strip("0"):
        info = look.fetch(f"{repo}@{before}...{head}",
                          f"/repos/{repo}/compare/{before}...{head}",
                          lambda c: {"n": c.get("ahead_by", 0),
                                     "msg": (c.get("commits") or [{}])[-1].get("commit", {}).get("message", "")})
    elif head:
        info = look.fetch(f"{repo}@{head}", f"/repos/{repo}/commits/{head}",
                          lambda c: {"n": 1, "msg": c.get("commit", {}).get("message", "")})
    where = f" to {br}" if br else ""
    if not info:
        return f"push{where}"
    n, msg = info.get("n", 0), clean(info.get("msg"))
    if n == 0:
        return f"force-push{where}"
    s = f"push{where} → {n} commit" + ("s" if n != 1 else "")
    return s + (" └ " + msg if msg else "")


def fmt_pr(e, repo, look):
    p = e.get("payload") or {}
    num = p.get("number") or (p.get("pull_request") or {}).get("number")
    action = p.get("action", "updated")
    if action == "closed" and (p.get("pull_request") or {}).get("merged"):
        action = "merged"
    s = f"{action} PR #{num}"
    if num:
        pr = look.fetch(f"{repo}#pr{num}", f"/repos/{repo}/pulls/{num}",
                        lambda r: {"title": r.get("title", "")})
        title = clean((pr or {}).get("title"))
        if title:
            s += " └ " + title
    return s


def fmt_ref(verb, p):
    rt = p.get("ref_type", "ref")
    if rt == "repository":
        return f"{verb}d repository"
    name = clean(p.get("ref"))
    return f"{verb} {rt}" + (f": {name}" if name else "")


def fmt(e, repo, look):
    t = e.get("type") or ""
    p = e.get("payload") or {}
    if t == "PushEvent":
        return fmt_push(e, repo, look)
    if t == "PullRequestEvent":
        return fmt_pr(e, repo, look)
    if t == "CreateEvent":
        return fmt_ref("create", p)
    if t == "DeleteEvent":
        return fmt_ref("delete", p)
    if t == "IssuesEvent":
        return f"{p.get('action', 'updated')} issue #{(p.get('issue') or {}).get('number', '?')}"
    if t == "IssueCommentEvent":
        return f"comment on #{(p.get('issue') or {}).get('number', '?')}"
    if t == "PullRequestReviewEvent":
        return f"review on PR #{(p.get('pull_request') or {}).get('number', '?')}"
    if t == "PullRequestReviewCommentEvent":
        return f"review comment on PR #{(p.get('pull_request') or {}).get('number', '?')}"
    if t == "ReleaseEvent":
        tag = clean((p.get("release") or {}).get("tag_name"))
        return "released" + (f" {tag}" if tag else "")
    if t == "PublicEvent":
        return "made public"
    if t == "WatchEvent":
        return "starred ★"
    if t == "ForkEvent":
        return "forked ⑂"
    if t == "GollumEvent":
        return "updated wiki"
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", t.removesuffix("Event")).lower()
    return words or "activity"


def build(look):
    repos = public_repos()
    kept = []
    for page in (1, 2, 3):  # GitHub keeps at most 300 recent events
        batch = get(f"/users/{USER}/events/public?per_page=100&page={page}")
        kept += [e for e in batch
                 if e.get("public") is True and (e.get("repo") or {}).get("name") in repos]
        if len(batch) < 100 or len(kept) >= MAX_EVENTS:
            break
    kept.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    out = []
    for e in kept[:MAX_EVENTS]:
        repo = e["repo"]["name"]
        out.append({
            "id": e.get("id"),
            "type": e.get("type"),
            "time": e.get("created_at"),
            "repo": repo,
            "repoUrl": "https://github.com/" + repo,
            "msg": fmt(e, repo, look),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="activity.json")
    ap.add_argument("--cache", default=None, help="lookup cache file")
    ap.add_argument("--hide", default=None, help="file of regexes to leave out")
    args = ap.parse_args()

    global HIDE
    if args.hide:
        with open(args.hide, encoding="utf-8") as f:
            pats = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        HIDE = re.compile("|".join(f"(?:{p})" for p in pats), re.I) if pats else None

    look = Lookups(args.cache)
    events = build(look)
    look.save()
    if not events:
        sys.exit("no public events; keeping the existing file")

    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "events": events,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out_dir, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.chmod(tmp, 0o644)
    os.replace(tmp, args.out)
    print(f"wrote {len(events)} events to {args.out} ({MAX_LOOKUPS - look.budget} lookups)")


if __name__ == "__main__":
    main()
