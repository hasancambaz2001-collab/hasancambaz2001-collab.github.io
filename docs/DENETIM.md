# Üretim Üssü — Kurulum Denetimi

Tarih: 2026-08-18 · Kapsam: `hasancambaz2001-collab/hasancambaz2001-collab.github.io` (tüm branch'ler, açık PR'lar, Actions, canlı site)

Bu bir kurulum/altyapı denetimidir. Strateji kârlılığı veya yatırım değerlendirmesi değildir.

---

## 1. Şu an nasıl kurulmuş

| Katman | Durum |
|---|---|
| Repo kimliği | GitHub Pages **user-site** reposu, **public** |
| Özel alan adı | `CNAME` → `dvgreenpass.com` |
| `main` | 2 commit: `README.md` + `CNAME`. Başka hiçbir şey yok. |
| Gerçek iş | 5 ayrı branch, **5 açık PR, 0 merge** |
| CI | Hiçbir branch'te `.github/workflows` yok. Tek workflow, Pages'in otomatik `pages-build-deployment`'ı. |
| Branch koruması | `main` korumasız (`protected: false`) |

### Branch'ler

Beşi de aynı base commit'ten (`38b3a95`) çatallanmış. İkisinin ortak atası da yine `38b3a95` — yani **hiçbiri diğerinin işini içermiyor**. Beş paralel silo.

| Branch | PR | Commit | Ne yapıyor |
|---|---|---|---|
| `cursor/whiskas-phase1-4921` | #3 | 69 | BTC 5m complete-set strateji araştırması. 238 dosya, 35 test dosyası. Asıl ağırlık burada. |
| `cursor/pipeline-research-verify-b262` | #4 | 4 | Ajan iş akışı: GOAL → RESEARCH → GATE → PLAN → BUILD → VERIFY + kilitler |
| `cursor/polymarket-edge-systems-1d37` | #5 | 2 | `polyedge` — fee-aware Polymarket tarayıcı + farm planlayıcı |
| `cursor/setup-dev-environment-4115` | #1 | 3 | `index.html` + live-server + `.nojekyll` |
| `cursor/setup-dev-environment-4d46` | #2 | 1 | Aynı işin ikinci, uyumsuz versiyonu (`python3 -m http.server`) |

---

## 2. Çalıştırıp doğruladıklarım

| Kontrol | Sonuç |
|---|---|
| `make verify` (pipeline branch) | **PASS** — 9 test, 3 fixture (0714 BLOCK / 0827 BLOCK / 0759 ALLOW), invariants |
| `pytest` (polyedge) | **18 passed** |
| `pytest` (whiskas) | **165 passed, 1 failed** |
| Sır/anahtar taraması (tüm branch'ler) | **Temiz.** `0x…` eşleşmeleri `condition_id` / order hash — hepsi zaten zincir üstünde public. |
| `.env` sızıntısı | **Yok.** `.env` + `.env.*` gitignore'da, sadece `configs/clob.env.example` commitli. Doğru kurulmuş. |

Yani parçalar tek tek çalışıyor. Sorun parçalarda değil, **birbirine bağlanmamış olmasında**.

---

## 3. Eksikler

### K1 — Üssün "üretim" tarafı boş
`main` iki dosya. 69 commit'lik whiskas, pipeline, polyedge, hatta `index.html` bile dışarıda. Ağustos'tan beri tek satır merge edilmemiş. Beş PR de aynı base SHA'ya bakıyor; ikisi (`4115` / `4d46`) doğrudan çakışıyor.

Sonuç: "üretim üssü" diye bakılan yerde üretilmiş hiçbir şey durmuyor. Tek gerçek kaynak branch listesi.

### K2 — Güvenlik kapısı boşa çalışıyor (en kritik)
`scripts/check_invariants.py` pipeline branch'inde. Denetlemesi gereken dosyalar ise whiskas branch'inde:

- `REQUIRED` = `configs/s1_micro.yaml` → pipeline branch'inde var, geçiyor. Ama bu dosya **sadece kilitleri yazan bir bildirim**; hiçbir kod onu okumuyor.
- `OPTIONAL` = `configs/generated/MICRO_LIVE_TRIAL.yaml` → pipeline branch'inde **yok**. Kontrol sessizce atlanıyor.
- `configs/whiskas.yaml` → **hiç denetlenmiyor**. Listede değil.

`check_invariants PASS` çıktısı bugün gerçek bir şeyi doğrulamıyor.

### K3 — Kilit çelişkisi
Aynı stratejinin iki farklı "kilit"i var ve ikisi birbirini görmüyor:

| | `docs/GOAL.md` + `s1_micro.yaml` (pipeline) | `configs/whiskas.yaml` (whiskas) |
|---|---|---|
| clip | **5** | **21** |
| pair_max | **0.90** | **0.96** (cap 0.97) |
| capital_max | **5000** | tanımsız |

GOAL "clip 5, no clip up" diyor; asıl strateji config'i 21'de duruyor. Hangisinin bağlayıcı olduğu repoda yazılı değil.

### K4 — CI yok
Tek `.github/workflows` yok. `make verify` yalnızca elle çalışıyor. Bir PR açıldığında hiçbir şey doğrulanmıyor, `main` korumasız — bugün her PR doğrudan merge edilebilir, kırık da olsa.

Kurulmuş bir verify altyapısı var ama tetikleyicisi yok.

### K5 — Temiz klonda test kırık
`tests/test_harness.py::test_tape_source_windows` → `FileNotFoundError: missing tape data/raw/mobo_bosona_activity.jsonl`.

Dosya `.gitignore`'da (`data/raw/*.jsonl`), doğru karar. Ama test bunu hesaba katmıyor. Yeni bir makinede suite baştan kırmızı — bu da "1 kırık normal" alışkanlığı yaratıyor, gerçek regresyon o gürültüde kaybolur. Doğrusu: veri yoksa `pytest.skip`, ya da küçük bir fixture commit'lemek.

### K6 — Public repo + canlı yayın yüzeyi
Repo public. Whiskas branch'inde canlı emir raporları (`data/reports/MICRO_ONE_LEG.md`), `live_orders: true` içeren `MICRO_LIVE_TRIAL.yaml` ve tam strateji parametreleri var. Sır sızıntısı **değil** — ama takip edilen cüzdan, eşikler ve emir zamanlaması dahil her şey açık.

Ayrıca bu bir Pages reposu: whiskas `main`'e merge edilirse aynı içerik `dvgreenpass.com` altından da servis edilir. `main`'de `.nojekyll` yok (o da `4115` branch'inde).

Özel repo `dvgreenpass` zaten mevcut ama 6 Temmuz'dan beri dokunulmamış.

### K7 — Site içeriği yayında değil
`index.html` sadece `4115` branch'inde. `main`'de olmadığı için `dvgreenpass.com` şu an Jekyll'in README'den ürettiği tek satırlık sayfayı gösteriyor. (Ağ bu ortamdan proxy tarafından kapalı olduğu için canlı yanıtı teyit edemedim; repo durumundan çıkan sonuç bu.)

### K8 — Küçük
- `numpy`, `whiskas/replay.py` içinde import ediliyor ama `pyproject.toml`'da yazılı değil. Şu an `pandas` üzerinden geliyor, kırılmıyor — ama örtük bir bağımlılık.
- `2×` dev-environment branch'i aynı işi farklı şekilde yapıyor; biri kapatılmalı.
- Kök `README.md` tek satır. Yeni gelen (veya 3 ay sonraki sen) neyin nerede olduğunu okuyamıyor.

---

## 4. Ne yapmalı — sıra önemli

**1. Tek gerçek kaynağı kur.** `4115`'i (site + `.nojekyll`) merge et, `4d46`'yı kapat. `main`'de çalışan bir site olsun.

**2. Kilit çelişkisini çöz.** clip 5 mi 21 mi, pair_max 0.90 mı 0.96 mı — biri bağlayıcı, diğeri geçmiş. Yazılı karar ver.

**3. Pipeline'ı whiskas ile aynı ağaca getir.** K2 ancak böyle kapanır. `check_invariants.py`'nin denetlediği liste, gerçekten kullanılan config'ler olmalı: `whiskas.yaml` ve `configs/generated/*.yaml`. Denetlenen dosya yoksa **PASS değil FAIL** vermeli — bugünkü "sessizce atla" davranışı kapının kendisini iptal ediyor.

**4. CI ekle.** `.github/workflows/verify.yml`: her PR'da `make verify`. Ardından `main`'e branch koruması + zorunlu check. Verify zaten yazılı, sadece tetiklenmiyor.

**5. K5'i düzelt.** Veri yoksa skip.

**6. Public/private ayrımına karar ver.** Strateji tarafı `dvgreenpass` (private) reposuna, site tarafı burada kalsın — ya da bilinçli olarak "hepsi açık" de. Şu anki durum karar değil, kaza.

**7. `README.md`'yi harita yap.** Hangi proje nerede, hangi branch canlı, ne ile doğrulanır.

---

## Özet

Parçalar iyi kurulmuş: kilit dili, fixture'lı verify, sır hijyeni, 165 geçen test, gerçekçi araştırma notları. Eksik olan **montaj**.

Beş silo, sıfır merge, sıfır CI, ve kendi koruduğu dosyayı göremeyen bir güvenlik kapısı. En kritik madde K2: `check_invariants PASS` bugün güvence vermiyor — çünkü denetlemesi gereken config'ler başka bir branch'te.
