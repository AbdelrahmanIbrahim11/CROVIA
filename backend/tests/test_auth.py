"""
Who may do what.

These exist because a real regression got through without one. While fixing the
citizen screen, which was polling an operator endpoint and being refused, the
guard on /api/state was changed from "operator" to "any signed-in account". The
screen worked again, and every citizen could read the headcounts, the API spend,
the panel size and the simulation ground truth. Nothing objected, because
nothing was checking.

Every test here is a rule that, if it ever fails, means somebody's data is
visible to somebody who should not see it. They run against the real app
through a test client, on a temporary database, with no network and no server.

    PYTHONPATH=. ./venv/bin/python tests/test_auth.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

# A throwaway database and a fixed signing key, set before the app is imported
# so it never touches the real one.
_TMP = tempfile.mkdtemp(prefix="crovia-test-")
os.environ["DATABASE"] = os.path.join(_TMP, "test.db")
os.environ["DATABASE_URL"] = ""
os.environ["JWT_SECRET"] = "a-fixed-key-for-tests"
os.environ["STAFF_INVITE_CODE"] = "test-invite"
os.environ["NOKIA_NAC_API_KEY"] = ""
os.environ["CROVIA_ENV"] = "local"

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import ratelimit  # noqa: E402
from app.auth.security import (create_access_token, decode_token,  # noqa: E402
                               hash_password, verify_password)
from app.main import app  # noqa: E402
from app.usersDB.db import create_table  # noqa: E402

create_table()
client = TestClient(app)


def _email() -> str:
    """A fresh address per account, so tests never collide."""
    return f"t{uuid.uuid4().hex[:10]}@example.com"


def _register(role: str = "normal", consent: bool = False, **over):
    # The username column is unique, so every test account needs its own name.
    # That constraint is itself a product problem - two real people called
    # Ahmed cannot both sign up - and it is recorded as a finding rather than
    # worked around here.
    body = {"username": f"Test {uuid.uuid4().hex[:8]}", "password": "a-good-password",
            "email": _email(), "user_type": role}
    if role == "normal":
        body["number"] = f"+9743{uuid.uuid4().int % 10_000_000:07d}"
        body["consent"] = consent
    else:
        body["invite_code"] = "test-invite"
    body.update(over)
    r = client.post("/auth/register", json=body)
    return body, r


def _token(role: str = "normal", consent: bool = False) -> tuple[str, dict]:
    body, r = _register(role, consent)
    assert r.status_code == 201, r.text
    ratelimit.clear(body["email"], "testclient")
    login = client.post("/auth/login", json={"email": body["email"],
                                             "password": body["password"],
                                             "user_type": role})
    assert login.status_code == 200, login.text
    return login.json()["access_token"], body


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def test_a_password_is_never_stored_as_typed():
    stored = hash_password("correct-horse")
    assert "correct-horse" not in stored
    assert stored.startswith("$2")


def test_the_right_password_is_accepted_and_a_wrong_one_is_not():
    stored = hash_password("correct-horse")
    assert verify_password("correct-horse", stored) is True
    assert verify_password("Correct-horse", stored) is False
    assert verify_password("", stored) is False


def test_a_damaged_hash_is_a_failed_login_not_a_crash():
    """
    Accounts made before the storage bug was fixed hold  b'$2b$12$...'  as
    text. Those must fail to log in, not take the server down.
    """
    assert verify_password("anything", "not-a-hash") is False
    assert verify_password("anything", None) is False


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def test_a_token_says_who_you_are():
    token, _ = create_access_token(user_id="abc", role="admin",
                                   username="Ops", email="o@example.com")
    claims = decode_token(token)
    assert claims["sub"] == "abc" and claims["role"] == "admin"


def test_a_tampered_token_is_refused():
    """The role travels inside the token, so changing it must break the signature."""
    token, _ = create_access_token(user_id="abc", role="normal",
                                   username="P", email="p@example.com")
    assert decode_token(token[:-1] + ("X" if token[-1] != "X" else "Y")) is None
    assert decode_token("not.a.token") is None
    assert decode_token("") is None


# ---------------------------------------------------------------------------
# Getting in
# ---------------------------------------------------------------------------

def test_a_wrong_password_is_refused():
    _, body = _token("normal")
    ratelimit.clear(body["email"], "testclient")
    r = client.post("/auth/login", json={"email": body["email"],
                                         "password": "not-the-password"})
    assert r.status_code == 401


def test_an_unknown_email_gives_the_same_answer_as_a_wrong_password():
    """Otherwise the endpoint tells a stranger which addresses are registered."""
    a = client.post("/auth/login", json={"email": _email(), "password": "whatever"})
    _, body = _token("normal")
    ratelimit.clear(body["email"], "testclient")
    b = client.post("/auth/login", json={"email": body["email"], "password": "wrong"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_a_short_phone_number_creates_nothing():
    """
    The account used to be written first and the number checked afterwards, so
    a short number left an account with no monitoring that could not be made
    again because the email was taken.
    """
    body, r = _register("normal", number="0100")
    assert r.status_code == 422
    again = client.post("/auth/login", json={"email": body["email"],
                                             "password": body["password"]})
    assert again.status_code == 401, "an account was left behind"


# ---------------------------------------------------------------------------
# Who may create a staff account
# ---------------------------------------------------------------------------

def test_a_stranger_cannot_make_themselves_an_operator():
    """
    This was possible: user_type came from the request body and was believed,
    so anyone who found the address could ask for "admin" and be given one.
    """
    for role in ("admin", "authority"):
        r = client.post("/auth/register", json={
            "username": "Attacker", "password": "a-good-password",
            "email": _email(), "user_type": role})
        assert r.status_code == 403, f"{role} was handed out with no invite code"


def test_a_wrong_invite_code_is_refused():
    r = client.post("/auth/register", json={
        "username": "Attacker", "password": "a-good-password",
        "email": _email(), "user_type": "admin", "invite_code": "guess"})
    assert r.status_code == 403


def test_anyone_may_make_a_citizen_account():
    """Citizen sign-up stays open. That is the product."""
    _, r = _register("normal")
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# The rules that regressed
# ---------------------------------------------------------------------------

OPERATIONS = ["/api/state", "/api/alerts", "/api/incidents", "/api/zones/operator"]


def test_operations_data_needs_a_token():
    for path in OPERATIONS:
        assert client.get(path).status_code == 401, path


def test_a_citizen_cannot_read_operations_data():
    """The exact regression: /api/state was opened to any signed-in account."""
    token, _ = _token("normal")
    for path in OPERATIONS:
        r = client.get(path, headers=_auth(token))
        assert r.status_code == 403, f"{path} leaked to a citizen ({r.status_code})"


def test_an_operator_can_read_operations_data():
    token, _ = _token("admin")
    for path in OPERATIONS:
        assert client.get(path, headers=_auth(token)).status_code == 200, path


def test_a_citizen_has_a_view_of_their_own():
    """Refusing the operator endpoint is only right if something replaces it."""
    token, _ = _token("normal", consent=True)
    r = client.get("/api/nearby", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert "zones" in body and "my_warnings" in body


def test_the_citizen_view_carries_no_operations_figures():
    token, _ = _token("normal", consent=True)
    body = client.get("/api/nearby", headers=_auth(token)).json()
    for zone in body["zones"].values():
        if zone:
            for secret in ("people_low", "people_high", "corridor_density"):
                assert secret not in zone, f"{secret} reached a citizen"
    for secret in ("spend", "monitored", "ground_truth", "unresolved"):
        assert secret not in body, f"{secret} reached a citizen"


def test_only_an_authority_may_close_an_incident():
    """Acknowledging is a record of responsibility, so it needs the right role."""
    operator, _ = _token("admin")
    fake = str(uuid.uuid4())
    r = client.post(f"/api/incidents/{fake}/acknowledge", headers=_auth(operator))
    assert r.status_code == 403

    authority, _ = _token("authority")
    r = client.post(f"/api/incidents/{fake}/acknowledge", headers=_auth(authority))
    # Allowed through the guard; 404 because that incident does not exist.
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# One person's data is not another's
# ---------------------------------------------------------------------------

def test_a_citizen_cannot_read_another_persons_warnings():
    token, _ = _token("normal", consent=True)
    r = client.get("/api/warnings/deadbeefdeadbeef", headers=_auth(token))
    assert r.status_code == 403


def test_a_citizen_cannot_change_another_persons_consent():
    """
    Without this check anyone signed in could switch off the monitoring that
    protects a stranger, or enrol a number that never agreed to anything.
    """
    token, mine = _token("normal", consent=True)
    r = client.request("DELETE", "/api/consent", headers=_auth(token),
                       json={"phone_number": "+97430009999"})
    assert r.status_code == 403

    ok = client.request("DELETE", "/api/consent", headers=_auth(token),
                        json={"phone_number": mine["number"]})
    assert ok.status_code == 200, "could not change their own"


def test_an_operator_account_has_no_warnings_of_its_own():
    """An operator watches the city; they are not the ones being warned."""
    token, _ = _token("admin")
    body = client.get("/api/warnings/me", headers=_auth(token)).json()
    assert body["warnings"] == []


# ---------------------------------------------------------------------------
# Slowing down guessing
# ---------------------------------------------------------------------------

def test_repeated_wrong_passwords_are_blocked():
    _, body = _token("normal")
    ratelimit.clear(body["email"], "testclient")
    codes = [client.post("/auth/login",
                         json={"email": body["email"], "password": f"guess-{i}"}).status_code
             for i in range(ratelimit.MAX_PER_EMAIL + 2)]
    assert 429 in codes, "passwords could be guessed without limit"
    ratelimit.clear(body["email"], "testclient")


# ---------------------------------------------------------------------------

def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  pass  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:
            failed += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
