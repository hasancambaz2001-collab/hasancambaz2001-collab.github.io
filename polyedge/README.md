# Polyedge

Polymarket’te **en tekrarlanabilir nakit**: iki taraflı maker (likidite ödülü + rebate) + holding sleeve.

Yön bahsi değil. Varsayılan **kâğıt**. Emir göndermez.

## Sistem

```bash
cd polyedge
pip install -r requirements.txt   # resmi Polymarket/py-sdk
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m polyedge farm --bankroll 2000 \
  --md-out snapshots/farm.md --json-out snapshots/farm.json
```

`farm` resmi `list_current_rewards` havuzlarını alır, 5dk crypto / mentions / ince defter / 48s içi settlement’i eler, post-only YES+NO bid üretir.

İsteğe bağlı:

| Altyapı | Nasıl bağlanır |
|---------|----------------|
| [Polymarket/py-sdk](https://github.com/Polymarket/py-sdk) | `pip install polymarket-client` (farm bunu kullanır) |
| [pmxt-dev/pmxt](https://github.com/pmxt-dev/pmxt) | `PMXT_API_KEY` + `farm --kalshi` |
| [warproxxx/poly_data](https://github.com/warproxxx/poly_data) | `POLY_DATA_DIR` → `processed/trades.csv` |
| [Jon-Becker/prediction-market-analysis](https://github.com/Jon-Becker/prediction-market-analysis) | `PMA_DATA_DIR` |

Canlı kotasyon motoru (paper önce): [warproxxx/poly-maker](https://github.com/warproxxx/poly-maker).

## Neden bu, BTC 5dk değil

Ağustos TWAP havuzları ($7500/gün, 1.5¢ band) HFT. Public bot orada evreni eksi. Kalın, ±3.5¢+ band, 48s+ vadeli politika/spor farm’ı protokol çekini alır.

Araştırma: [RESEARCH.md](RESEARCH.md). Canlı plan: [snapshots/farm.md](snapshots/farm.md).

Yasal erişim sizin işiniz. Geo-bypass yok. Yatırım tavsiyesi değil.
