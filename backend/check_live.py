"""
Prove the deployed service can RECEIVE from Nokia, not just ask it.

There are two directions, and only one is easy to test. Asking Nokia takes a
key and a curl. Nokia asking us takes a public address, which is the thing a
laptop cannot have and a deployment can - so this only became possible once the
service was hosted.

What it does, in one run:

  1. makes a citizen account, so there is somebody to warn
  2. makes an operator account, because enrolling a device needs one
  3. enrols a Nokia test phone, which is what tells Nokia where to send
  4. waits, keeping the service awake, and reports what arrived

Step 3 is the important one. Creating a subscription is the only way to say
"send notifications to https://.../webhooks/...", and until that happens Nokia
has no reason to contact you at all.

    PYTHONPATH=. ./venv/bin/python check_live.py https://crovia.onrender.com CODE

Both arguments are optional; the defaults are the deployed service.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://crovia.onrender.com").rstrip("/")
INVITE = sys.argv[2] if len(sys.argv) > 2 else "Sa4LPxESBMrRnbOc"

# Nokia's test phone that reports itself as inside the area.
TEST_PHONE = "+99999991001"
# How long to wait for a notification. Congestion arrives every few minutes per
# device, so anything shorter than this would report failure too early.
WAIT_S = 360
PASSWORD = "crovia-live-check"


def call(method, path, body=None, token=None, timeout=120):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={k: v for k, v in {
            "Content-Type": "application/json" if body is not None else None,
            "Authorization": f"Bearer {token}" if token else None,
        }.items() if v})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:200]}
    except Exception as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    tag = uuid.uuid4().hex[:6]
    citizen_email = f"citizen-{tag}@example.com"
    ops_email = f"ops-{tag}@example.com"
    # A number of its own, so this run never collides with a real account.
    citizen_phone = f"+9743{uuid.uuid4().int % 10_000_000:07d}"

    print("=" * 70)
    print(f"Checking {BASE}")
    print("=" * 70)

    print("\n1. waking the service (the free plan sleeps after 15 minutes)")
    t0 = time.time()
    s, b = call("GET", "/health", timeout=180)
    if s != 200:
        print(f"   the service did not answer: {s} {b}")
        return 1
    print(f"   awake after {time.time() - t0:.0f}s - {b.get('city')}")

    print("\n2. creating a citizen account")
    s, b = call("POST", "/auth/register", {
        "username": f"Citizen {tag}", "password": PASSWORD, "email": citizen_email,
        "number": citizen_phone, "consent": True})
    if s != 201:
        print(f"   could not create it: {s} {b}")
        return 1
    print(f"   {citizen_email}  /  {PASSWORD}")
    print(f"   monitored: {b.get('monitored')}  (consent was given)")

    print("\n3. creating an operator account (enrolling a device needs one)")
    s, b = call("POST", "/auth/register", {
        "username": f"Ops {tag}", "password": PASSWORD, "email": ops_email,
        "user_type": "admin", "invite_code": INVITE})
    if s != 201:
        print(f"   could not create it: {s} {b}")
        print("   check the invite code matches STAFF_INVITE_CODE on the server")
        return 1
    print(f"   {ops_email}  /  {PASSWORD}")

    s, b = call("POST", "/auth/login", {"email": ops_email, "password": PASSWORD,
                                        "user_type": "admin"})
    token = b.get("access_token")
    if not token:
        print(f"   could not sign in: {s} {b}")
        return 1

    print(f"\n4. enrolling {TEST_PHONE} - this is what tells Nokia where to send")
    call("POST", "/api/consent", {"phone_number": TEST_PHONE}, token=token)
    s, b = call("POST", "/api/enrol", {
        "phone_number": TEST_PHONE, "role": "sentinel",
        "district_id": "district_stadium"}, token=token, timeout=180)
    subs = b.get("subscriptions") or []
    if not subs:
        print(f"   no subscriptions were created: {s} {b}")
        print("   without a NOKIA_NAC_API_KEY the server uses its own simulator,")
        print("   which never sends anything back.")
        return 1
    for sub in subs:
        print(f"   created: {sub}")
    if b.get("warning"):
        print(f"   warning: {b['warning']}")

    print(f"\n5. waiting up to {WAIT_S // 60} minutes for Nokia to send something")
    print("   (each dot is a check, and also keeps the service awake)")
    deadline = time.time() + WAIT_S
    placed = False
    while time.time() < deadline:
        time.sleep(20)
        print(".", end="", flush=True)
        s, state = call("GET", "/api/state", token=token, timeout=90)
        if s != 200:
            continue
        # NOT proof of anything on its own.
        #
        # Enrolling with a district places the device locally from the signup
        # hint, before Nokia is involved at all - so this number goes up
        # whether or not a notification ever arrives. It is shown because it is
        # useful, not because it proves delivery.
        located = (state.get("monitored") or {}).get("located", 0)
        if located and not placed:
            placed = True
            print(f"\n   {located} device(s) placed (from the signup hint, not proof)")
        busy = [d for d, st in (state.get("districts") or {}).items() if st != "IDLE"]
        if busy:
            print(f"\n   a congestion notification arrived - {busy} is no longer idle")
            break

    print("\n\n" + "=" * 70)
    s, state = call("GET", "/api/state", token=token, timeout=90)
    mon = (state.get("monitored") or {}) if s == 200 else {}
    print(f"  devices enrolled : {mon.get('sentinels', '?')}")
    print(f"  devices located  : {mon.get("located", "?")}")
    print(f"  calls spent      : {(state.get('spend') or {}).get('total', '?')}")
    print()
    print("  Whether Nokia actually SENT anything can only be read from the")
    print("  server's own log. Nothing in the API proves it, because enrolling")
    print("  places a device locally from the signup hint either way.")
    print()
    print("  Open Render -> Logs and look for lines like:")
    print("    35.242.195.147 - \"POST /webhooks/geofencing/<hash>\" 200 OK")
    print("    35.242.195.147 - \"POST /webhooks/congestion/<hash>\" 200 OK")
    print()
    print("  That address is Nokia. Those lines are the only real evidence.")
    print()
    print("  Note: the simulator sends congestion at confidence 9, and CROVIA")
    print("  ignores anything below 50 - so a notification can arrive, be")
    print("  correctly discarded, and change nothing you can see from outside.")
    print()
    print("  sign in to the app with:")
    print(f"    citizen   {citizen_email}  /  {PASSWORD}")
    print(f"    operator  {ops_email}  /  {PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
