#!/usr/bin/env python3
"""Polygon proxy → EOA → sibling proxies. No bot."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.constants import WHISKAS_WALLET
from whiskas.http import get_json

RPC = "https://polygon-bor-rpc.publicnode.com"
IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
WALLET_DEPLOYED = "0x7441de0ad639fe5d2bf1c22447715a0528b682385736bb40ae8dd92555eb8276"
FACTORIES = [
    "0xaB45c5A4B0c941a2F231C04C3f49182e1A254052",  # Polymarket Proxy Factory
    "0xaacFeEa03eb1561C4e67d661e40682Bd20E3541b",  # Gnosis Safe Factory
    "0x7A18EDfe055488A3128f01F563e5B479D92ffc3a",  # Deposit Wallet Beacon
]


def rpc(method: str, params: list) -> dict:
    req = urllib.request.Request(
        RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "whiskas-research/0.1"},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read())


def addr_from_word(word: str | None) -> str | None:
    if not word or word == "0x":
        return None
    h = word[2:].rjust(64, "0")
    a = "0x" + h[-40:]
    if a == "0x" + "0" * 40:
        return None
    return a.lower()


def topic_addr(addr: str) -> str:
    return "0x" + addr[2:].lower().rjust(64, "0")


def main() -> int:
    proxy = WHISKAS_WALLET.lower()
    impl_word = rpc("eth_getStorageAt", [proxy, IMPL_SLOT, "latest"]).get("result")
    impl = addr_from_word(impl_word)
    owner_word = rpc("eth_call", [{"to": proxy, "data": "0x8da5cb5b"}, "latest"]).get("result")
    eoa = addr_from_word(owner_word)
    eoa_code = (rpc("eth_getCode", [eoa, "latest"]).get("result") if eoa else None) or "0x"
    eoa_nonce = rpc("eth_getTransactionCount", [eoa, "latest"]).get("result") if eoa else None

    profile_eoa = None
    if eoa:
        try:
            profile_eoa = get_json(
                "https://gamma-api.polymarket.com/public-profile",
                {"address": eoa},
                timeout=20,
                retries=2,
                pause=0.05,
            )
        except Exception as exc:
            profile_eoa = {"error": str(exc)}

    siblings: list[str] = []
    log_errors: list[str] = []
    if eoa:
        owner_topic = topic_addr(eoa)
        for factory in FACTORIES:
            try:
                res = rpc(
                    "eth_getLogs",
                    [
                        {
                            "fromBlock": "0x0",
                            "toBlock": "latest",
                            "address": factory,
                            "topics": [WALLET_DEPLOYED, None, owner_topic],
                        }
                    ],
                )
                logs = res.get("result") or []
                if res.get("error"):
                    log_errors.append(f"{factory}: {res['error']}")
                    continue
                for log in logs:
                    topics = log.get("topics") or []
                    if len(topics) >= 2:
                        w = addr_from_word(topics[1])
                        if w and w != proxy:
                            siblings.append(w)
            except Exception as exc:
                log_errors.append(f"{factory}: {exc}")

    siblings = sorted(set(siblings))
    out = {
        "proxy": proxy,
        "implementation": impl,
        "eoa": eoa,
        "eoa_code_prefix": eoa_code[:20],
        "eoa_is_contract": len(eoa_code) > 2 and not eoa_code.startswith("0xef0100"),
        "eoa_eip7702": eoa_code.startswith("0xef0100"),
        "eoa_nonce": eoa_nonce,
        "profile_on_eoa": profile_eoa,
        "siblings": siblings,
        "cluster": bool(siblings),
        "log_errors": log_errors,
        "notes": [
            "owner() on the EIP-1967 deposit-wallet proxy returns the EOA.",
            "Polymarket factory derives one CREATE2 proxy per EOA.",
            "Gamma profile on the EOA points at the same proxy; EOA traded=0.",
        ],
    }
    dest = ROOT / "data" / "processed" / "cluster_stats.json"
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
