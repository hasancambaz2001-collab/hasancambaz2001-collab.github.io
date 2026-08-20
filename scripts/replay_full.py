#!/usr/bin/env python3
"""FULL KASA replay on their tape. S1 only (paper_maker primary). No live.

Default = their size (parity their-size). --clip 10 = parity clip10.
pair_gt_1_trade=false. Do not treat paper intends as PnL.
usd_ratio = clip10 $ / their-size $ is computed — never a hardcoded percent.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.kasa import CLIP_NOW, is_s1, load_all_windows, quantile, s1_pnl

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"


def usd_ratio(clip_usd: float, their_usd: float) -> float | None:
    """clip10 / their-size from the two $ figures. Never a hardcoded percent."""
    if their_usd <= 0:
        return None
    return float(clip_usd) / float(their_usd)


def size_stats(windows: list, *, clip: float) -> dict:
    sizes = [float(w["maker_matched"]) for w in windows if w.get("maker_matched") is not None]
    n = len(sizes)
    size_sum = float(sum(sizes))
    clip_size_sum = float(clip) * n
    return {
        "n": n,
        "clip": float(clip),
        "their_size_sum": size_sum,
        "clip_size_sum": clip_size_sum,
        "size_sum_ratio": (clip_size_sum / size_sum) if size_sum > 0 else None,
        "their_size_mean": (size_sum / n) if n else None,
        "their_size_min": min(sizes) if sizes else None,
        "their_size_p25": quantile(sizes, 0.25),
        "their_size_p50": quantile(sizes, 0.50),
        "their_size_p75": quantile(sizes, 0.75),
        "their_size_p90": quantile(sizes, 0.90),
        "their_size_max": max(sizes) if sizes else None,
        "n_their_gt_clip": sum(1 for s in sizes if s > float(clip) + 1e-12),
        "n_their_le_clip": sum(1 for s in sizes if s <= float(clip) + 1e-12),
    }


def compare_parity(
    *,
    their_usd: float,
    clip_usd: float,
    n_their: int,
    n_clip: int,
    windows: list | None = None,
    clip: float = CLIP_NOW,
) -> dict:
    ratio = usd_ratio(clip_usd, their_usd)
    same_n = n_their == n_clip
    payload = {
        "parity_their_size": float(their_usd),
        "parity_clip10": float(clip_usd),
        "n_their": int(n_their),
        "n_clip10": int(n_clip),
        "same_n": same_n,
        "usd_ratio": ratio,
        "clip10_lt_their": float(clip_usd) < float(their_usd),
        "gap_usd": float(their_usd) - float(clip_usd),
        "kind": "size_gap" if same_n else "mixed",
        "note": (
            "Same S1 windows and pairs; only size changes (paper clip vs their matched). "
            "usd_ratio = parity_clip10 / parity_their_size, computed, not hardcoded."
        ),
        "size_ok": False,
        "pair_gt_1_trade": False,
        "pnl_from_paper_intends": False,
    }
    if windows is not None:
        payload["size"] = size_stats(windows, clip=clip)
        by: dict[str, dict[str, float | int | None]] = {}
        for w in windows:
            name = str(w.get("wallet") or "?")
            cell = by.setdefault(name, {"n": 0, "their_usd": 0.0, "clip10_usd": 0.0})
            cell["n"] = int(cell["n"]) + 1
            cell["their_usd"] = float(cell["their_usd"]) + s1_pnl(w)
            cell["clip10_usd"] = float(cell["clip10_usd"]) + s1_pnl(w, clip=clip)
        for cell in by.values():
            t = float(cell["their_usd"])
            cell["usd_ratio"] = (float(cell["clip10_usd"]) / t) if t > 0 else None
        payload["wallets"] = by
    return payload


def _write_compare(cmp: dict) -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / "replay_full_compare.json").write_text(json.dumps(cmp, indent=2) + "\n")
    md = REPORTS / "REPLAY_FULL.md"
    prev = md.read_text(encoding="utf-8") if md.is_file() else (
        "# REPLAY_FULL\n\nTheir tape. S1 maker pair<0.90. pair_gt_1_trade=false.\n\n"
    )
    ratio = cmp.get("usd_ratio")
    ratio_s = "n/a" if ratio is None else f"{ratio:.6f} ({100.0 * ratio:.4f}% of their-size $)"
    size = cmp.get("size") or {}
    block_lines = [
        "## clip10 vs their-size",
        "",
        f"- parity their-size = **{cmp['parity_their_size']:.2f}** n={cmp['n_their']}",
        f"- parity clip10 = **{cmp['parity_clip10']:.2f}** n={cmp['n_clip10']}",
        f"- usd_ratio (clip10 / their-size) = **{ratio_s}** — computed from the two $ figures",
        f"- clip10 << their-size: **{cmp['clip10_lt_their']}** · gap_usd = **{cmp['gap_usd']:.2f}**",
        f"- kind = **{cmp['kind']}** (same n={cmp['same_n']}; only size changes)",
    ]
    if size:
        p50 = size.get("their_size_p50")
        mean = size.get("their_size_mean")
        sratio = size.get("size_sum_ratio")
        block_lines.extend(
            [
                f"- their matched size: n={size.get('n')} sum={size.get('their_size_sum'):.4f} "
                f"mean={None if mean is None else round(mean, 4)} "
                f"p25={size.get('their_size_p25')} p50={p50} p75={size.get('their_size_p75')} "
                f"p90={size.get('their_size_p90')} max={size.get('their_size_max')}",
                f"- paper clip size sum = {size.get('clip_size_sum'):.4f} · "
                f"size_sum_ratio = {None if sratio is None else round(sratio, 6)}",
                f"- windows with their size > clip: {size.get('n_their_gt_clip')} / {size.get('n')}",
            ]
        )
    wallets = cmp.get("wallets") or {}
    if wallets:
        block_lines.append("")
        block_lines.append("| wallet | n | their-size $ | clip10 $ | usd_ratio |")
        block_lines.append("|---|---:|---:|---:|---:|")
        for name, cell in wallets.items():
            r = cell.get("usd_ratio")
            block_lines.append(
                f"| {name} | {cell['n']} | {float(cell['their_usd']):.2f} | "
                f"{float(cell['clip10_usd']):.2f} | {'' if r is None else f'{r:.6f}'} |"
            )
    block_lines.extend(["", cmp["note"], ""])
    block = "\n".join(block_lines)
    if "## clip10 vs their-size" in prev:
        head, _sep, rest = prev.partition("## clip10 vs their-size")
        nxt = rest.find("\n## ")
        tail = rest[nxt:] if nxt >= 0 else ""
        prev = head.rstrip() + "\n\n" + block + tail
    else:
        prev = prev.rstrip() + "\n\n" + block + "\n"
    md.write_text(prev, encoding="utf-8")


def _maybe_compare(windows: list) -> dict | None:
    their_p = PROC / "replay_full_their-size.json"
    clip_p = PROC / "replay_full_clip10.json"
    if not (their_p.is_file() and clip_p.is_file()):
        return None
    their = json.loads(their_p.read_text(encoding="utf-8"))
    clip = json.loads(clip_p.read_text(encoding="utf-8"))
    cmp = compare_parity(
        their_usd=float(their["usd"]),
        clip_usd=float(clip["usd"]),
        n_their=int(their["n"]),
        n_clip=int(clip["n"]),
        windows=windows,
        clip=float(clip.get("clip") or CLIP_NOW),
    )
    _write_compare(cmp)
    return cmp


def main() -> int:
    parser = argparse.ArgumentParser(description="FULL KASA S1 replay. No live.")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--clip", type=float, default=None, help="fixed clip; omit = their size")
    parser.add_argument("--compare", action="store_true", help="write clip10 vs their-size from the two $ figures")
    args = parser.parse_args()
    if not args.run and not args.compare:
        print(f"SCAFFOLD {Path(__file__).name} (pass --run)", flush=True)
        return 0
    windows = [w for w in load_all_windows(ROOT) if is_s1(w)]
    if args.run:
        clip = args.clip
        usd = sum(s1_pnl(w, clip=clip) for w in windows)
        label = "clip10" if clip is not None and abs(float(clip) - CLIP_NOW) < 1e-12 else (
            f"clip{clip:g}" if clip is not None else "their-size"
        )
        payload = {
            "book": "S1",
            "primary": "paper_maker",
            "ask_fok_primary": False,
            "pair_gt_1_trade": False,
            "clip": clip,
            "label": label,
            "n": len(windows),
            "usd": usd,
            "pnl_from_paper_intends": False,
        }
        PROC.mkdir(parents=True, exist_ok=True)
        REPORTS.mkdir(parents=True, exist_ok=True)
        out_json = PROC / f"replay_full_{label}.json"
        out_json.write_text(json.dumps(payload, indent=2) + "\n")
        md = REPORTS / "REPLAY_FULL.md"
        prev = md.read_text(encoding="utf-8") if md.is_file() else (
            "# REPLAY_FULL\n\nTheir tape. S1 maker pair<0.90. pair_gt_1_trade=false.\n\n"
        )
        line = (
            f"- parity {label} = **{usd:.2f}** n={len(windows)} clip={clip} "
            f"({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})"
        )
        if re.search(rf"^- parity {re.escape(label)} =", prev, flags=re.M):
            prev = re.sub(rf"^- parity {re.escape(label)} =.*$", line, prev, flags=re.M)
        else:
            prev = prev.rstrip() + "\n\n" + line + "\n"
        md.write_text(prev, encoding="utf-8")
        print(json.dumps({"parity": label, "usd": round(usd, 2), "n": len(windows), "clip": clip, "pair_gt_1_trade": False}))
    cmp = _maybe_compare(windows)
    if args.compare or cmp is not None:
        if cmp is None:
            print(json.dumps({"compare": False, "reason": "need both replay_full_their-size.json and replay_full_clip10.json"}))
            return 1
        print(json.dumps({
            "compare": True,
            "parity_their_size": round(cmp["parity_their_size"], 2),
            "parity_clip10": round(cmp["parity_clip10"], 2),
            "usd_ratio": cmp["usd_ratio"],
            "clip10_lt_their": cmp["clip10_lt_their"],
            "kind": cmp["kind"],
            "size_ok": False,
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
