# Polyedge

Polymarket üzerinde **gerçekten tekrarlanabilir** para akışlarını ayıklayan araştırma tarayıcısı.

Emir göndermez. Private key istemez. Kâğıt / araştırma.

## Sert gerçek

GitHub’da “polymarket bot” diye yıldız toplayan çoğu repo **para basmaz**.

- CLOB V2 (28 Nisan 2026) V1 SDK’ları üretimde öldürdü.
- Taker fee = `shares × rate × p × (1−p)`. Ham YES+NO < $1 çoğu zaman **ücret illüzyonu**.
- Cüzdanların büyük çoğunluğu yön bahsinde eksi.
- Tekrarlanabilir nakit, protokolün ödediği tarafta: likidite ödülü, maker rebate, holding reward.

Bu repo o ayrımı kodlar. Tam liste ve gerekçe: [RESEARCH.md](RESEARCH.md).

## Ne tarar

1. **Likidite ödülü** — günlük havuz / kalabalık skoru (ince defter, yüksek $/gün).
2. **Holding reward** — ~%3.25–4 APY açık long-dated marketler.
3. **Completeness** — YES+NO, **ücret sonrası** net edge (al-her-iki veya split+sat).
4. **Neg-risk Dutch book** — mutually exclusive YES ask toplamı < $1 − fee.

## Kurulum

Python 3.10+, ekstra paket yok.

```bash
cd polyedge
PYTHONPATH=src python3 -m polyedge scan \
  --max-markets 1200 \
  --max-events 40 \
  --max-books 350 \
  --md-out snapshots/latest.md \
  --json-out snapshots/latest.json
```

Test:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Canlı para için (bu repo değil)

Protocol yield’i fiilen farm etmek için public tarafta en ciddi bot:

- [warproxxx/poly-maker](https://github.com/warproxxx/poly-maker) — CLOB V2, **sadece maker / post-only**, inventory skew, reward band, `--paper`, kill switch.

Önce paper. Küçük size. İki taraflı kotasyon. Haber anında kotasyonu çek.

Yasal / coğrafi kısıtlar sizin sorumluluğunuz. Geo-bypass veya KYC kaçırma yok.
