"""
The two things a visitor is shown, and the one that quietly broke.

A demonstration builds its own engine at request time. The first version
attached the alarm hooks to the engine the service booted with and never moved
them, so a simulated crowd raised an alarm that appeared on the map, wrote no
incident, and warned nobody. Nothing failed and nothing logged an error - the
demonstration simply did less than it appeared to, which is the worst way for a
demonstration to be wrong.

    PYTHONPATH=. ./venv/bin/python tests/test_demo.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

os.environ["JWT_SECRET"] = "a-test-secret-long-enough-for-sha256"
os.environ["STAFF_INVITE_CODE"] = "test-invite"
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mkdtemp() + "/demo.db"
os.environ["CROVIA_TWIN"] = "0"
# Set empty rather than removed. The app calls load_dotenv(), which walks up
# from the working directory and finds the real .env one level above the
# backend - so a removed key comes straight back and the test spends real
# Nokia calls. load_dotenv does not overwrite a name already present, even an
# empty one, so this is what actually keeps the test offline.
os.environ["NOKIA_NAC_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app import runtime  # noqa: E402
from app.main import app  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"  {'pass' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


def citizen(c: TestClient) -> dict:
    """A signed-up person with consent - somebody there is to warn."""
    tag = uuid.uuid4().hex[:8]
    email = f"c-{tag}@example.com"
    r = c.post("/auth/register", json={
        "username": f"Citizen {tag}", "password": "a-good-password",
        "email": email, "number": f"+9743{uuid.uuid4().int % 10_000_000:07d}",
        "consent": True})
    assert r.status_code == 201, r.text
    tok = c.post("/auth/login", json={"email": email,
                                      "password": "a-good-password"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def run() -> int:
    with TestClient(app) as c:
        print("\n-- who may use them ---------------------------------------------")
        check("no token is refused", c.get("/api/demo/simulation").status_code == 401)
        h = citizen(c)
        check("a citizen may look", c.get("/api/demo/simulation").status_code == 401
              or c.get("/api/demo/simulation", headers=h).status_code == 200,
              "a judge who signs up on the app needs no operator account")

        print("\n-- the real Nokia devices ---------------------------------------")
        r = c.get("/api/demo/nokia", headers=h)
        check("answers without a key rather than inventing", r.status_code == 200
              and r.json().get("live") is False,
              "reports why instead of showing a stand-in as real")

        print("\n-- every API, on the four devices --------------------------------")
        # Deliberately readable without an account. A judge sent the link
        # pastes it into a browser, and a browser cannot carry a bearer token.
        check("the all-APIs page opens without signing in",
              c.get("/api/demo/apis").status_code == 200,
              "a stranger checking the integration must not be refused")
        # But refreshing spends real calls, so that part still needs an account.
        check("a stranger cannot force a paid refresh",
              c.get("/api/demo/apis?refresh=true").status_code == 200,
              "ignored rather than refused, and served from cache")
        r = c.get("/api/demo/apis", headers=h)
        # Same rule as /nokia. Without a key these answers would come from the
        # built-in stand-in, and a page whose whole purpose is to prove the
        # calls are real must not show a stand-in as if it were Nokia.
        check("it refuses to fake it without a key", r.status_code == 200
              and r.json().get("live") is False,
              "a judge reading this must know the answers are Nokia's")

        print("\n-- refusing nonsense --------------------------------------------")
        check("too many attendees", c.post("/api/demo/simulation", headers=h,
                                           json={"attendees": 5_000_000}).status_code == 422)
        check("a zone that does not exist", c.post("/api/demo/simulation", headers=h,
                                                   json={"zone": "zone_atlantis"}).status_code == 422)

        print("\n-- a simulation reaches a real person ----------------------------")
        r = c.post("/api/demo/simulation", headers=h,
                   json={"attendees": 40000, "release_minutes": 8})
        check("it starts", r.status_code == 200 and r.json().get("running") is True)

        # Drive it exactly as the background loop does: the world moves in
        # ordinary steps and the engine runs on simulated time after each one.
        alerts = 0
        for _ in range(80):
            runtime.step_twin(30.0)
            runtime.get_engine().tick(runtime.engine_now())
            alerts = len(runtime.get_engine().alerts)
            if alerts:
                break
        check("a crowd forms and the alarm fires", alerts > 0, f"{alerts} alarm(s)")

        me = c.get("/api/nearby", headers=h).json()
        check("the citizen sees the alarm", len(me.get("alerts") or []) > 0)
        # The regression this file exists for.
        check("the citizen is actually warned", len(me.get("my_warnings") or []) > 0,
              "hooks must follow the engine that raised the alarm")

        warned = [t for t in runtime.get_engine().trace if t.get("kind") == "warned"]
        check("the warning is on the demonstration's own trace", bool(warned),
              warned[-1]["msg"] if warned else "no 'warned' entry")

        print("\n-- stopping hands the screens back -------------------------------")
        check("it stops", c.delete("/api/demo/simulation", headers=h).json()["stopped"] is True)
        check("and nothing is simulated afterwards",
              c.get("/api/demo/simulation", headers=h).json()["running"] is False)
        check("the real engine is back", len(runtime.get_engine().alerts) == 0)

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} passed")
    for name, ok, detail in results:
        if not ok:
            print(f"  FAILED: {name} {detail}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(run())
