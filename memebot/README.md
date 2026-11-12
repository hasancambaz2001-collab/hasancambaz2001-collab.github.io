# memebot: filtreli memecoin girişi + 3x'te anaparayı otomatik kurtarma

pump.fun akışını gerçek zamanlı izler. Önce çöpü eler, sinyal skoru tutan token'a otomatik girer.
Elindeki çantanın net değeri 3x'e ulaştığında **yatırdığın parayı geri çeken kadarını satar**,
kalanı "bedava pozisyon" olarak kademeli satış ve trailing stop ile yönetir.

> **Uyarı:** Bu bir araçtır, para basma makinesi değil. Varsayılan parametreler **kalibre edilmemiş
> tahminlerdir.** Sentetik simülasyonda iyi görünmesi gerçek piyasada edge olduğunu göstermez.
> Gerçek parayla çalıştırmadan önce aşağıdaki doğrulama adımlarını uygula.

## Nasıl çalışır

```
PumpPortal WS ──► TokenState (holder, dev, sniper, akış metrikleri)
                     │
                     ▼
          1) KALICI ELEME  dev alımı > %8 · sniper > %15 · seri launcher
          2) GİRİŞ PENCERESİ  yaş 60s–15dk · mcap 60–350 SOL (curve) / migration sonrası hayatta kalma
          3) CANLI ELEME  top10 > %35 · dev çantasının > %50'sini satmış
          4) SKOR (6'da ≥4)  benzersiz alıcı · alış/satış oranı · net giriş · yeni alıcı · dağınık alımlar · momentum
                     │
          RİSK  max açık pozisyon · toplam risk · 24 saatlik zarar limiti · saatlik giriş · kill switch
                     │
                     ▼
               ALIM (paper / live)
                     │
   ┌─────────────────┴──────────────────────────────────────────────┐
   │ Anapara kurtarılmadan önce:                                     │
   │   rug tespiti (dev satışı / tek satışta %35 düşüş) → hepsini sat│
   │   stop-loss %45 · 2x gördükten sonra 1x'e düşerse breakeven     │
   │   30 dk içinde 3x olmazsa time stop                             │
   │   NET değer ≥ 3x → maliyeti geri getirecek kadarını sat (~%35)  │
   │ Anapara kurtarıldıktan sonra (bedava pozisyon):                 │
   │   10x / 30x / 100x'te ilk çantanın %25'ini sat                  │
   │   zirveden %50 geri çekilirse kalanı sat                        │
   └─────────────────────────────────────────────────────────────────┘
```

"3x" fiyat üzerinden değil, **fee, slippage ve price impact düşüldükten sonra elde edilecek SOL**
üzerinden hesaplanır. Bot ancak gerçekten parayı geri alabileceği an tetiklenir.

## Kurulum

```bash
cd memebot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q          # 16 test
```

## Kullanım: doğrulama sırasıyla

| Adım | Komut | Ne yapar |
|---|---|---|
| 0. Demo | `python -m memebot simulate --tokens 3000` | Sentetik piyasada uçtan uca çalıştırır. Sadece tesisatı test eder |
| 1. Veri topla | `python -m memebot record` | Canlı akışı `data/stream-*.jsonl` dosyasına kaydeder (paper trade de yapar). **En az 1–2 hafta** |
| 2. Backtest | `python -m memebot -c config.toml replay data/stream-*.jsonl` | Kayıtlı gerçek veride stratejiyi çalıştırır. Parametreleri burada ayarla |
| 3. Paper | `python -m memebot -c config.toml paper` | Canlı akış, sahte para, gecikme + slippage modeliyle. **En az 2 hafta** |
| 4. Live | aşağıya bak | Gerçek para. Küçük başla |
| Rapor | `python -m memebot report data/journal-*.jsonl` | Win rate, anapara kurtarma oranı, PnL, drawdown, çıkış nedenleri |

Durdurmak için: `touch data/STOP` yeni girişleri anında keser. Ctrl+C açık pozisyonları kapatıp çıkar.

### Live mod

```bash
export MEMEBOT_PRIVATE_KEY="<base58 key: SADECE bu iş için açılmış ayrı cüzdan>"
export MEMEBOT_LIVE_CONFIRM=YES
python -m memebot -c config.toml live
```

- **Ayrı bir hot wallet aç**, içine sadece kaybetmeyi göze aldığın kadar SOL koy. Ana cüzdanını asla kullanma.
- Key sadece env değişkeninden okunur. Config dosyasında `private`, `secret` veya `seed` geçen bir alan varsa bot çalışmayı reddeder. `.gitignore` key, `.env` ve `data/` dosyalarını hariç tutar.
- `rpc_url` olarak ücretli bir RPC kullan (Helius, Triton, QuickNode). Public RPC rate limit'e takılır.
- Fill'ler quote'tan değil, **on-chain bakiye farkından** hesaplanır.
- Canlıya geçmeden önce PumpPortal `trade-local` istek alanlarını güncel dokümanla karşılaştır. Bu ortamdan pumpportal.fun'a erişim yoktu, entegrasyon canlı test edilmedi.

## Sentetik test sonuçları (kanıt değildir)

3000 token'lık sentetik piyasa. Gizli insider dump'ları ve 1,5 saniye gecikme modellendi.

| Runner oranı (varsayım) | İşlem | Kazanma | Anapara kurtarma | ROI |
|---|---|---|---|---|
| %1 | ~225 | %19–24 | %18–22 | +%16 … +%46 |
| %0,2 | ~145 | %12–14 | %12–14 | +%2 … +%9 |

Ana ders: **sonuç, gerçek dünyadaki runner oranına ve giriş sonrası dump hızına bağlı.** Bu iki
parametreyi sentetik veri söyleyemez. Sadece 1. ve 2. adımdaki gerçek kayıtlar söyleyebilir.
Kazanma oranı düşük, getiri birkaç büyük kazanana bağlı. Bu yüzden pozisyon başına risk küçük
tutulmalı.

## Bilinen sınırlar ve sonraki adımlar

- **Fonlama grafiği yok:** Holder'ların aynı kaynaktan fonlanıp fonlanmadığına bakılmıyor. Helius/Bitquery ile eklenebilir. Gizli insider kümelerini yakalamanın en güçlü yolu bu.
- **Smart money cüzdan takibi yok.**
- **Migration sonrası paper fiyatlaması tahmini:** Havuz derinliği `amm_depth_ratio` ile modelleniyor.
- **MEV / sandwich:** `slippage_pct=15` sandwich bot'larına alan bırakır. Live'da Jito bundle ya da daha düşük slippage değerlendirilmeli.
- **Parametre overfitting:** Replay'de en iyi parametreyi bulup paper'da test etmeden live'a geçme. Walk-forward uygula: 1. haftada ayarla, 2. haftada test et.

## Dosyalar

```
memebot/
  events.py     PumpPortal mesaj parser
  curve.py      bonding curve / AMM matematiği
  features.py   token başına on-chain metrikler
  filters.py    eleme + sinyal skoru
  positions.py  çıkış politikası (3x anapara kurtarma, ladder, trailing, rug)
  risk.py       portföy limitleri, kill switch
  executor.py   PaperExecutor (curve + gecikme) / LiveExecutor (PumpPortal + RPC)
  engine.py     olay güdümlü orkestrasyon
  feed.py       canlı WS + kayıt + replay
  sim.py        sentetik piyasa (test/demo)
  journal.py    JSONL işlem defteri + rapor
```
