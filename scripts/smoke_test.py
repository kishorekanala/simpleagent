"""Post-deploy smoke test for the agent service.

Usage:
  ID_TOKEN=$(gcloud auth print-identity-token) python scripts/smoke_test.py https://SERVICE-URL
  python scripts/smoke_test.py http://localhost:8080      # local, no token needed
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

APP = "simpleagent"


def call(base: str, method: str, path: str, body: dict | None = None) -> object:
    headers = {"Content-Type": "application/json"}
    if token := os.getenv("ID_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)  # noqa: S310
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        return json.loads(resp.read())


def check(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit(f"Smoke test FAILED: {message}")


def main(base: str) -> int:
    base = base.rstrip("/")
    check(call(base, "GET", "/health") == {"status": "ok"}, "health check failed")
    check(APP in call(base, "GET", "/list-apps"), f"{APP} not served")

    user = "smoke-test"
    question = "What is 2 + 2? Reply with digits."
    session = call(base, "POST", f"/apps/{APP}/users/{user}/sessions", {})
    start = time.monotonic()
    events = call(
        base,
        "POST",
        "/run",
        {
            "appName": APP,
            "userId": user,
            "sessionId": session["id"],
            "newMessage": {"role": "user", "parts": [{"text": question}]},
        },
    )
    latency = time.monotonic() - start
    reply = "".join(
        p.get("text") or "" for e in events for p in (e.get("content") or {}).get("parts") or []
    )
    check("4" in reply, f"unexpected reply: {reply!r}")
    print(f"Smoke test passed in {latency:.2f}s: {reply.strip()!r}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
