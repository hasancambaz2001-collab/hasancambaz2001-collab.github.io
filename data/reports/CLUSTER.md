# CLUSTER — proxy → EOA → siblings

**Cluster: no.**

| | |
|---|---|
| Proxy (traded) | `0x3048d65321be3497164cdfc2996f94f98a2e7537` |
| Implementation (EIP-1967) | `0x58ca52ebe0dadfdf531cde7062e76746de4db1eb` (Polymarket Deposit Wallet Impl) |
| `owner()` | **`0x07c187878ad505ac0a275cf8471b64670d01efae`** |
| EOA code | `0xef0100…` (EIP-7702 delegation, not a contract wallet) |
| EOA nonce | `1` |
| EOA traded (Data API) | 0 |
| Gamma profile on EOA | same user `x-MoneyForWhiskas`, **same proxy** |
| Sibling proxies | **none found** |

Polymarket’s proxy factory is CREATE2: one implementation salt = `keccak256(abi.encodePacked(eoA))` → one proxy per EOA. The EOA’s public profile points at this proxy only. Factory `WalletDeployed` log scan over the full chain was blocked by the public RPC 10k-block cap; the 1:1 factory math plus nonce=1 plus identical Gamma profile is enough to say **no sibling cluster**.

We did not find a second proxy or a second Polymarket username for this key. If they have other EOAs, those are a different cluster and not visible from this proxy.
