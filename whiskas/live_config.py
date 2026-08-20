"""Live config gates. PAPER is the only runnable config. No hand-edited live.

G5/G6 default FAIL until ops flags exist. LIVE_READY only with flags + --i-accept-risk.
Do not print PMDATA keys. No pair>1. No clip 67 day-one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

COVER_MIN = 0.80
PAPER_CLIP = 10.0
PAIR_MAX = 0.90
CANCEL_ABOVE = 0.92
ASSETS = ("btc", "eth", "sol", "xrp", "doge")
TFS = ("5m", "15m")
MAX_CLIP_HARD = 21.0
MAX_DAILY_LOSS = 100.0

G5_FLAG = Path("data/ops/G5_size_ok.flag")
G6_FLAG = Path("data/ops/G6_fill_calibrated.flag")
PAPER_ONLY = Path("configs/generated/PAPER_ONLY.yaml")
LIVE_BLOCKED = Path("configs/generated/LIVE_BLOCKED.yaml")
LIVE_READY = Path("configs/generated/LIVE_READY.yaml")
ENV_PMDATA = Path("configs/.env.pmdata")


def load_pmdata_env(path: Path | None = None) -> bool:
    """Load configs/.env.pmdata into os.environ. Never print values."""
    p = path or ENV_PMDATA
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


def ensure_pmdata_env_file(path: Path | None = None) -> Path:
    """Write env file from process env if missing. Never log the key."""
    p = path or ENV_PMDATA
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_file() and p.stat().st_size > 0:
        return p
    key = os.environ.get("PMDATA_API_KEY") or os.environ.get("PM_DATA_API_KEY") or ""
    body = "# Do not commit. Do not print this file.\n"
    if key:
        body += f"PMDATA_API_KEY={key}\n"
    else:
        body += "PMDATA_API_KEY=\n"
    p.write_text(body, encoding="utf-8")
    return p


def load_activity(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    jsonl = path.suffix == ".jsonl" or (
        len(lines) > 1 and lines[0].startswith("{") and lines[1].startswith("{")
    )
    if jsonl:
        out: list[dict[str, Any]] = []
        for line in lines:
            rec = json.loads(line)
            if isinstance(rec, dict):
                out.append(rec)
        return out
    data = json.loads(text)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        rows = data.get("activity") or data.get("rows") or []
        return [r for r in rows if isinstance(r, dict)]
    return []


def dump_jsonl_to_json(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    rows = load_activity(src)
    dest.write_text(json.dumps(rows) + "\n", encoding="utf-8")
    return dest


def flag_exists(path: Path) -> bool:
    return path.is_file()


def evaluate_gates(
    *,
    bosona_cover: float | None,
    mo_cover: float | None,
    pair_gt_1_trade: bool,
    shadow_only: bool,
    g5_flag: Path | None = None,
    g6_flag: Path | None = None,
    cover_min: float = COVER_MIN,
    accept_risk: bool = False,
) -> dict[str, Any]:
    g5 = flag_exists(g5_flag or G5_FLAG)
    g6 = flag_exists(g6_flag or G6_FLAG)
    g1 = bosona_cover is not None and float(bosona_cover) + 1e-12 >= float(cover_min)
    g2 = mo_cover is not None and float(mo_cover) + 1e-12 >= float(cover_min)
    g3 = pair_gt_1_trade is False
    g4 = bool(shadow_only)
    g7 = bool(accept_risk)
    gates = {
        "G1_bosona_cover": {"pass": g1, "cover": bosona_cover, "min": cover_min},
        "G2_mo_cover": {"pass": g2, "cover": mo_cover, "min": cover_min},
        "G3_pair_gt1_trade": {"pass": g3, "pair_gt_1_trade": pair_gt_1_trade},
        "G4_shadow_path": {"pass": g4, "shadow_only": shadow_only},
        "G5_size_ok": {"pass": g5, "flag": str(g5_flag or G5_FLAG), "note": "FAIL until human size_ok flag"},
        "G6_fill_calibration": {
            "pass": g6,
            "flag": str(g6_flag or G6_FLAG),
            "note": "FAIL until paper fill% logged vs sim + human flag",
        },
        "G7_accept_risk": {"pass": g7, "note": "FAIL until --i-accept-risk"},
    }
    blocked = not (g5 and g6)
    return {
        "gates": gates,
        "all_selection": g1 and g2 and g3 and g4,
        "g5_g6": g5 and g6,
        "g7": g7,
        "live_blocked": blocked or not (g1 and g2 and g3 and g4) or not g7,
        "cover_min": cover_min,
    }


def paper_only_payload() -> dict[str, Any]:
    return {
        "live_orders": False,
        "live": False,
        "clip": PAPER_CLIP,
        "interval": 1.0,
        "pair_max": PAIR_MAX,
        "cancel_above": CANCEL_ABOVE,
        "assets": list(ASSETS),
        "tfs": list(TFS),
        "pair_gt_1_trade": False,
        "size_ok": False,
        "primary": "paper_maker",
        "smart_copy": {"shadow_only": True},
        "notes": "PAPER only. do not live without G5 G6. No clip 67 day-one.",
    }


def live_blocked_payload(*, gates: dict[str, Any] | None = None) -> dict[str, Any]:
    body = paper_only_payload()
    body.update(
        {
            "status": "LIVE_BLOCKED",
            "live_orders": False,
            "live": False,
            "size_ok": False,
            "notes": "LIVE_BLOCKED. do not live without G5 G6. No hand-edited LIVE_READY.",
        }
    )
    if gates is not None:
        body["gates"] = {
            k: ("PASS" if v.get("pass") else "FAIL") for k, v in gates.items()
        }
    return body


def live_ready_payload() -> dict[str, Any]:
    body = paper_only_payload()
    body.update(
        {
            "live_orders": True,
            "live": True,
            "clip": PAPER_CLIP,
            "max_clip_hard": MAX_CLIP_HARD,
            "max_daily_loss": MAX_DAILY_LOSS,
            "kill_switch": True,
            "size_ok": True,
            "notes": "LIVE_READY only after G5+G6+--i-accept-risk. clip stays 10. max_clip_hard=21.",
        }
    )
    return body


def write_yaml(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def live_status(*, eval_gates: dict[str, Any], accept_risk: bool) -> str:
    if (
        not eval_gates.get("g5_g6")
        or not accept_risk
        or not eval_gates.get("all_selection")
    ):
        return "LIVE_BLOCKED"
    return "LIVE_READY"
