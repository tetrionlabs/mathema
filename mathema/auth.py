# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Human verification for the decision verbs: a PIN a person knows and
an agent does not, so an acceptance (or an unlock) carries evidence a
human made it.

The mechanism is a tripwire and an attestation, not a cryptographic
barrier: on a machine where an agent has unrestricted shell, absolute
prevention is impossible. What this buys is that the decision verbs
cannot be driven in the normal course of agentic work, and subversion
(resetting the PIN, editing records by hand) leaves auditable traces:
every verified decision is stamped with the key id of the credential
that authorised it, so a reviewer can see which credential signed and
whether it is the one currently configured.

The secret lives at user level (`~/.config/mathema/auth.yaml`, mode
0600), never inside a project tree, since an agent working in a
repository reads project files freely. Records carry only the key id.

Two methods share one prompt and one stamp:

- ``pin``: a memorised 4-12 digit PIN, stored as a salted PBKDF2 hash.
- ``totp``: RFC 6238 time-based codes from any authenticator app
  (the 6-digit codes that change every 30 seconds). Implemented and
  tested; not yet the promoted path.

The ``verified_by: {method, key}`` stamp is an open shape: an
enterprise deployment verifying against its own security layer (SSO,
hardware keys) stamps the same two facts its own way.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import struct
import time


class HumanVerificationError(Exception):
    """Verification was required and did not happen: no interactive
    terminal, a wrong code, or a policy the configured method fails."""


_PBKDF2_ITERATIONS = 600_000
_TOTP_STEP = 30
_TOTP_DIGITS = 6
_ATTEMPTS = 3


def _config_dir() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")
    return os.path.join(base, "mathema")


def config_path() -> str:
    """Where the credential lives: `~/.config/mathema/auth.yaml`
    (respecting `XDG_CONFIG_HOME`). User-level deliberately: a project
    tree is readable by any agent working in it, and `.mathema/` is
    committed besides."""
    return os.path.join(_config_dir(), "auth.yaml")


def configured() -> dict | None:
    """The stored credential record (never the code itself), or None
    when no PIN is set, which switches the whole feature off."""
    import yaml
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except OSError:
        return None
    return data if data.get("method") in ("pin", "totp") else None


def _write_config(data: dict) -> None:
    import yaml
    os.makedirs(_config_dir(), exist_ok=True)
    path = config_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write("# mathema human-verification credential. Never commit\n"
                "# this file. Records reference it by `key` only.\n")
        yaml.safe_dump(data, f, sort_keys=False)
    os.chmod(path, 0o600)


def _key_id(material: bytes) -> str:
    return hashlib.sha256(material).hexdigest()[:6]


def set_pin(pin: str) -> dict:
    """Store a static PIN (salted, slow-hashed). Returns the public
    part: `{key, method}`. Refuses a weak shape rather than a weak
    value: 4-12 digits, since the threat is an agent, not an attacker
    with the hash file."""
    if not re.fullmatch(r"\d{4,12}", pin):
        raise HumanVerificationError("a PIN is 4-12 digits")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt,
                                 _PBKDF2_ITERATIONS)
    data = {"key": _key_id(salt + digest), "method": "pin",
            "salt": salt.hex(), "pin_hash": digest.hex(),
            "created": time.strftime("%Y-%m-%d")}
    _write_config(data)
    return {"key": data["key"], "method": "pin"}


def set_totp() -> dict:
    """Store a fresh TOTP secret. Returns `{key, method, secret, uri}`;
    the secret and otpauth URI are shown ONCE for enrolment into an
    authenticator app and are not printed again."""
    raw = secrets.token_bytes(20)
    secret = base64.b32encode(raw).decode().rstrip("=")
    data = {"key": _key_id(raw), "method": "totp", "secret": secret,
            "created": time.strftime("%Y-%m-%d")}
    _write_config(data)
    user = os.environ.get("USER", "user")
    uri = (f"otpauth://totp/mathema:{user}?secret={secret}"
           f"&issuer=mathema&digits={_TOTP_DIGITS}&period={_TOTP_STEP}")
    return {"key": data["key"], "method": "totp",
            "secret": secret, "uri": uri}


def remove() -> bool:
    """Delete the credential. True if one existed."""
    try:
        os.remove(config_path())
        return True
    except OSError:
        return False


def _totp_code(secret: str, counter: int) -> str:
    pad = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + pad, casefold=True)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** _TOTP_DIGITS)).zfill(_TOTP_DIGITS)


def verify_code(code: str, *, record: dict | None = None,
                now: float | None = None) -> bool:
    """Check one entered code against the stored credential. For TOTP
    the current 30-second window and its two neighbours are accepted
    (ordinary clock skew)."""
    record = record if record is not None else configured()
    if record is None:
        return False
    code = (code or "").strip()
    if record["method"] == "pin":
        digest = hashlib.pbkdf2_hmac("sha256", code.encode(),
                                     bytes.fromhex(record["salt"]),
                                     _PBKDF2_ITERATIONS)
        return hmac.compare_digest(digest.hex(), record["pin_hash"])
    counter = int((now if now is not None else time.time()) // _TOTP_STEP)
    return any(hmac.compare_digest(_totp_code(record["secret"], counter + d),
                                   code)
               for d in (-1, 0, 1))


def _tty_available() -> bool:
    """Whether a controlling terminal exists to prompt on. Its own
    function so the refusal path is testable without a real tty."""
    try:
        with open("/dev/tty", "r", encoding="utf-8"):
            return True
    except OSError:
        return False


def _prompt_code(action: str) -> str:
    """Read a code from the controlling terminal, and only from there:
    a caller without a real `/dev/tty` (a pipe, a captured subprocess)
    is refused rather than silently read from stdin, since the entire
    point is that the code arrives from a person at a keyboard."""
    if not _tty_available():
        raise HumanVerificationError(
            f"{action} requires human verification (a PIN is set), which "
            f"needs an interactive terminal; run this command yourself "
            f"rather than through a non-interactive caller")
    import getpass
    try:
        # getpass reads from /dev/tty itself (no echo); the check
        # above already refused the callers that would make it fall
        # back to a pipeable stdin
        return getpass.getpass("PIN: ")
    except EOFError as e:
        raise HumanVerificationError(
            f"{action}: PIN entry aborted; nothing written") from e


def prompt_new_pin() -> str:
    """Read a new PIN twice from the controlling terminal (no echo),
    for `mathema pin set`/`rotate`. Same terminal-only rule as
    verification: a non-interactive caller is refused."""
    if not _tty_available():
        raise HumanVerificationError(
            "setting a PIN needs an interactive terminal")
    import getpass
    first = getpass.getpass("choose a PIN (4-12 digits): ")
    second = getpass.getpass("confirm: ")
    if first != second:
        raise HumanVerificationError("the two entries differ; nothing set")
    return first


def require_human(action: str) -> dict | None:
    """The gate the decision verbs call before writing. No credential
    configured: returns None and the write proceeds (the feature is
    opt-in). Credential configured: prompts on the controlling
    terminal, up to three attempts, and returns the attestation
    `{"method": ..., "key": ...}` to stamp into the record; anything
    else raises `HumanVerificationError` and nothing is written."""
    record = configured()
    if record is None:
        return None
    for _ in range(_ATTEMPTS):
        code = _prompt_code(action)
        if verify_code(code, record=record):
            return {"method": record["method"], "key": record["key"]}
    raise HumanVerificationError(
        f"{action}: PIN verification failed after {_ATTEMPTS} attempts; "
        f"nothing written")


# --- project policy ---------------------------------------------------------

def load_policy(root: str = ".") -> dict:
    """The project's acceptance policy: `.mathema/meta/policy.yaml`'s
    `acceptance:` section, `{}` when absent. Committed and human-owned,
    it holds only public constraints (required methods, allowed key
    ids), never a secret:

        acceptance:
          require_verification: true   # every acceptance carries verified_by
          methods: [totp]              # omitting pin disables the static PIN
          keys: [a3f2c1]               # optional allowlist of key ids
    """
    import yaml
    path = os.path.join(root, ".mathema", "meta", "policy.yaml")
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except OSError:
        return {}
    section = data.get("acceptance")
    return section if isinstance(section, dict) else {}


def enforce_policy(attestation: dict | None, root: str = ".") -> None:
    """The write-time gate: raises when the project's policy forbids
    this acceptance. No policy, no constraint; a policy with
    `require_verification` refuses an unverified write outright, and
    `methods`/`keys` narrow which credentials count."""
    policy = load_policy(root)
    if not policy:
        return
    if attestation is None:
        if policy.get("require_verification"):
            raise HumanVerificationError(
                "this project's policy requires human-verified "
                "acceptances (.mathema/meta/policy.yaml); set a "
                "credential with `mathema pin set` and retry")
        return
    methods = policy.get("methods")
    if methods and attestation.get("method") not in methods:
        raise HumanVerificationError(
            f"this project's policy accepts only {', '.join(methods)} "
            f"verification; the configured credential is "
            f"{attestation.get('method')} (rotate with `mathema pin`)")
    keys = policy.get("keys")
    if keys and attestation.get("key") not in keys:
        raise HumanVerificationError(
            f"the configured credential ({attestation.get('key')}) is "
            f"not in this project's allowed key list; a policy owner "
            f"must add it to .mathema/meta/policy.yaml")


def acceptance_policy_problems(key: str, entry: dict,
                               policy: dict) -> list[str]:
    """The verify-time check (the CI gate): every non-stale acceptance
    in a record must carry a `verified_by` the policy accepts. Returns
    problem strings; empty without a policy."""
    if not policy or not policy.get("require_verification"):
        return []
    problems = []
    methods = policy.get("methods")
    keys = policy.get("keys")

    def _check(owner: str, accepted: dict) -> None:
        if not isinstance(accepted, dict) or accepted.get("stale"):
            return
        vb = accepted.get("verified_by")
        if not isinstance(vb, dict):
            problems.append(
                f"{key}: {owner} acceptance is not human-verified, and "
                f"this project's policy requires it (re-accept with a "
                f"credential set)")
            return
        if methods and vb.get("method") not in methods:
            problems.append(
                f"{key}: {owner} acceptance was verified by "
                f"{vb.get('method')}, outside the policy's methods")
        if keys and vb.get("key") not in keys:
            problems.append(
                f"{key}: {owner} acceptance was signed by key "
                f"{vb.get('key')}, not in the policy's allowed list")

    for c in entry.get("claims") or []:
        if c.get("accepted"):
            _check(f"claim {c.get('name')!r}", c["accepted"])
    if entry.get("intent_accepted"):
        _check("intent", entry["intent_accepted"])
    return problems
