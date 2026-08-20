"""Load CLOB/L2 keys from env or local file. Never print values. Never commit keys."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ENV_CLOB = Path("configs/.env.clob")
# Accepted names. Do not use PMDATA_API_KEY.
PRIVATE_KEY_NAMES = ("POLYMARKET_PRIVATE_KEY", "CLOB_PRIVATE_KEY", "PRIVATE_KEY")
API_KEY_NAMES = ("CLOB_API_KEY", "POLY_API_KEY")
API_SECRET_NAMES = ("CLOB_API_SECRET", "POLY_API_SECRET")
API_PASS_NAMES = ("CLOB_API_PASSPHRASE", "POLY_API_PASSPHRASE", "POLY_PASSPHRASE")
FUNDER_NAMES = ("POLYMARKET_FUNDER", "CLOB_FUNDER", "FUNDER")
SIG_TYPE_NAMES = ("CLOB_SIGNATURE_TYPE", "SIGNATURE_TYPE")


def load_env_file(path: Path | None = None) -> bool:
    """Load KEY=value lines into os.environ if missing. Never logs values."""
    p = path or ENV_CLOB
    if not p.is_file():
        return False
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:
            os.environ[key] = val
    return True


def _first(names: tuple[str, ...]) -> tuple[str | None, str | None]:
    for name in names:
        val = os.environ.get(name)
        if val:
            return name, val
    return None, None


def creds_present() -> dict[str, Any]:
    """Which credential *names* are set. Never returns secret values."""
    load_env_file()
    pk_name, _pk = _first(PRIVATE_KEY_NAMES)
    key_name, _k = _first(API_KEY_NAMES)
    sec_name, _s = _first(API_SECRET_NAMES)
    pass_name, _p = _first(API_PASS_NAMES)
    funder_name, _f = _first(FUNDER_NAMES)
    sig_name, sig_val = _first(SIG_TYPE_NAMES)
    l2 = bool(key_name and sec_name and pass_name)
    return {
        "private_key_env": pk_name,
        "api_key_env": key_name,
        "api_secret_env": sec_name,
        "api_passphrase_env": pass_name,
        "funder_env": funder_name,
        "signature_type_env": sig_name,
        "has_private_key": bool(pk_name),
        "has_l2_creds": l2,
        "auth_available": bool(pk_name) and l2,
        "can_derive_l2": bool(pk_name) and not l2,
    }


def load_secrets() -> dict[str, Any] | None:
    """Return secrets for client build only. Caller must not print."""
    load_env_file()
    _pk_name, pk = _first(PRIVATE_KEY_NAMES)
    _k_name, api_key = _first(API_KEY_NAMES)
    _s_name, api_secret = _first(API_SECRET_NAMES)
    _p_name, api_pass = _first(API_PASS_NAMES)
    _f_name, funder = _first(FUNDER_NAMES)
    _sig_name, sig = _first(SIG_TYPE_NAMES)
    if not pk:
        return None
    sig_type = 0
    if sig is not None and str(sig).strip().lstrip("-").isdigit():
        sig_type = int(sig)
    return {
        "private_key": pk,
        "api_key": api_key,
        "api_secret": api_secret,
        "api_passphrase": api_pass,
        "funder": funder,
        "signature_type": sig_type,
    }


def auth_status() -> dict[str, Any]:
    info = creds_present()
    if info["auth_available"]:
        reason = "l2_ready"
    elif info["can_derive_l2"]:
        reason = "private_key_only_no_l2"
    else:
        reason = "AUTH_ABSENT"
    return {
        "auth_available": bool(info["auth_available"]),
        "reason": reason,
        "private_key_env": info["private_key_env"],
        "api_key_env": info["api_key_env"],
        "api_secret_env": info["api_secret_env"],
        "api_passphrase_env": info["api_passphrase_env"],
        "funder_env": info["funder_env"],
        "note": "values never printed. AUTH_ABSENT => do not send, do not fake real_fill.",
    }
