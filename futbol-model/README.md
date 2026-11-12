# İddaa Tahmin Motoru: literatüre dayalı, kör backtest'li futbol modeli

Bu klasör maç başına **150+ bahis marketinin** olasılığını üreten bir model içerir.
Model akademik literatürden seçildi ve geçmiş sonuçlar üzerinde **kör (blind) walk-forward backtest** ile doğrulandı.

> **Sonuçların özeti** için `results/holdout_results.json` ve aşağıdaki
> "Kör test sonuçları" bölümüne bakın.

## 1. Literatürde ne işe yarıyor?

| Çalışma | Bulgu | Bu sistemde |
|---|---|---|
| Maher (1982), *Statistica Neerlandica* | Takım hücum/savunma gücüyle Poisson gol modeli | Temel yapı |
| Dixon & Coles (1997), *JRSS C* 46(2) | Düşük skor düzeltmesi (ρ) ve zamanla azalan ağırlık; bahis piyasasında verimsizlik | Ana gol modeli |
| Karlis & Ntzoufras (2003), *The Statistician* | Bivariate Poisson ile beraberlik tahmini iyileşir | ρ düzeltmesi aynı işi görür |
| Ley, Van de Wiele & Van Eetvelde (2019), *Statistical Modelling* 19(1) | Çeşitli ML modelleri karşılaştırılmış; en iyisi zaman ağırlıklı (yarı ömür ≈ 390 gün) Poisson tipi modeller | ξ zaman sönümü ayarlandı |
| Baio & Blangiardo (2010); Egidi, Pauli & Torelli (2018), *Statistical Modelling* | Takım etkilerinde Bayesçi büzüştürme ve bahis oranlarıyla birleştirme doğruluğu artırır | Ridge önsel + piyasa havuzu |
| Wheatcroft (2020), *Int. J. Forecasting* 36(3) | Şut/korner tabanlı "GAP" reytingleri Alt/Üst'te golden daha iyi | İsabetli şut tabanlı sözde-xG |
| Wheatcroft (2021), *JQAS* 17(4) | RPS yerine log-skor (ignorance) önerilir | Ana ölçüt log-loss |
| Constantinou & Fenton (2012, 2013), *JQAS* | RPS ölçütü; pi-ratings | RPS raporlanıyor |
| Hubáček, Šourek & Železný (2019), *Machine Learning* 108 | 2017 Soccer Prediction Challenge birincisi: pi-ratings + gradient boosting | Gelecek iş (bkz. §6) |
| Berrar, Lopes & Dubitzky (2019); Constantinou (2019) "Dolores", *Machine Learning* 108 | Reyting özellikleri + ML / Bayes ağı | – |
| Koopman & Lit (2015), *JRSS A* | Dinamik bivariate Poisson; bahiste kâr iddiası | Zaman sönümü benzer işi görür |
| Boshnakov, Kharrat & McHale (2017), *IJF* | Weibull sayım modeli daha iyi kalibrasyon | – |
| Forrest, Goddard & Simmons (2005), *IJF*; Štrumbelj & Šikonja (2010) | Bahisçi oranları en iyi tek tahmin kaynağıdır | Piyasa ölçüt (benchmark) olarak alındı |
| Shin (1993), *Economic Journal*; Štrumbelj (2014), *IJF* | Oranlardan marj ayıklama | Shin (1X2), power (2'li marketler) |
| Kelly (1956); Thorp | Optimal pay büyüklüğü | ¼ Kelly, %2.5 tavan |

**Sonuç:** "En iyi tek model" diye bir şey yok. Sağlam bir çekirdek **zaman ağırlıklı Dixon-Coles** modelidir.
Bunu üç ekleme güçlendirir: şut verisinden türetilen sözde-xG, büzüştürme önseli ve **piyasa oranlarıyla birleştirme**.
Skor dağılımı tam olarak üretildiği için iddaanın bütün gol marketleri aynı modelden tutarlı biçimde türetilir.

## 2. Sistem mimarisi

```
data.py      Football-Data.co.uk (238k maç, 22 Avrupa ligi + Süper Lig): skor, İY, şut, korner, kart, B365 ve en iyi oranlar
model.py     Dixon-Coles (zaman sönümlü + ridge + sözde-xG), korner ve kart için negatif binom takım modelleri
markets.py   Skor matrisinden tüm marketler: MS, ÇŞ, DNB, A/Ü 0.5-5.5, KG, TG aralığı, tek/çift,
             takım golleri, gol yemeden kazanma, MS+A/Ü, handikaplı MS, Asya handikap, doğru skor,
             İY 1X2, İY A/Ü, 2Y 1X2, İY/MS, daha çok gol olan yarı, korner A/Ü + 1X2, kart A/Ü + 1X2
odds.py      Shin / power ile marj ayıklama
backtest.py  Haftalık walk-forward: her pazartesi SADECE o tarihten önceki maçlarla fit edilir, sonraki 7 günü tahmin eder
evaluate.py  Log-loss, Brier, RPS, kalibrasyon, piyasa havuzu, bahis simülasyonu, bootstrap güven aralığı, Kelly
tune.py      1. adım: tüm parametreler SADECE doğrulama döneminde (2016/17-2018/19) ayarlanır ve dondurulur
holdout.py   2. adım: dondurulmuş parametrelerle 2019/20 sonrası kör test (tek sefer)
predict.py   Tek maç için tam market listesi, adil oranlar ve verilen oranlara göre EV
```

### Kör test protokolü
1. **Ayarlama (validation):** 2016-07 → 2019-06. Bu dönemde ayarlananlar: ξ, ridge, şut ağırlığı, korner/kart parametreleri, piyasa havuzu ağırlıkları ve bahis eşikleri.
2. **Dondurma:** `config/frozen_params.json` ayrı bir commit olarak kaydedilir. Git zaman damgası, kör testten önce dondurulduğunun kanıtıdır.
3. **Kör test (holdout):** 2019-07 → 2026-09. Tek koşu yapılır, sonuca göre yeniden ayar yapılmaz.
4. Her tahmin yalnızca maç haftasından önceki verilerle yapılır, yani sızıntı (leakage) yoktur.

## 3. Kullanım

```bash
pip install numpy pandas scipy
python3 tune.py       # ~15 dk, config/frozen_params.json üretir
python3 holdout.py    # kör test, results/ altına yazar
python3 predict.py --div T1 --home Galatasaray --away Fenerbahce
python3 predict.py --div E0 --home Arsenal --away Chelsea --odds 1=2.10 X=3.50 2=3.60 O2.5=1.85 U2.5=2.00 KG_VAR=1.75
```
