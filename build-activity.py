#!/usr/bin/env python3
"""Pre-render Indigo's GitHub activity feed into activity.json.

Why this exists: the site previously fetched GitHub's public events API
directly from every visitor's browser. That endpoint is unauthenticated and
rate-limited to 60 requests/hour PER IP. Any visitor (or anyone behind a
shared/NAT IP, or a privacy blocker) that hits that limit gets a 403 and the
"system activity" panel on the right renders blank.

This script runs server-side with an authenticated `gh` token (5,000/hr, not
IP-shared) and writes a static activity.json the browser loads locally. No
per-visitor rate limit, no CORS, no blocker exposure.
"""
import json
import subprocess
import datetime
import sys


def gh_api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def fmt(e):
    t = e.get("type")
    p = e.get("payload") or {}
    if t == "PushEvent":
        commits = p.get("commits") or []
        n = len(commits)
        s = f"push → {n} commit" + ("s" if n != 1 else "")
        if commits:
            m = (commits[0].get("message") or "").split("\n")[0]
            if m:
                s += " └ " + m
        return s
    if t == "CreateEvent":
        rt = p.get("ref_type", "ref")
        ref = p.get("ref")
        return "create " + rt + (": " + ref if ref else "")
    if t == "IssuesEvent":
        return f"{p.get('action', '?')} issue #{p.get('issue', {}).get('number', '?')}"
    if t == "PullRequestEvent":
        return f"{p.get('action', '?')} PR #{p.get('pull_request', {}).get('number', '?')}"
    if t == "IssueCommentEvent":
        return f"comment on #{p.get('issue', {}).get('number', '?')}"
    if t == "WatchEvent":
        return "starred ★"
    if t == "ForkEvent":
        return "forked ⑂"
    if t == "ReleaseEvent":
        return "released " + (p.get("release", {}).get("tag_name") or "")
    return t


def main():
    data = gh_api("/users/indigokarasu/events?per_page=30")
    events = []
    for e in data:
        repo = (e.get("repo") or {}).get("name", "?")
        events.append({
            "type": e.get("type"),
            "time": e.get("created_at"),
            "repo": repo,
            "repoUrl": "https://github.com/" + repo,
            "msg": fmt(e),
        })
    out = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "events": events,
    }
    with open("activity.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"wrote {len(events)} events -> activity.json")


if __name__ == "__main__":
    main()
