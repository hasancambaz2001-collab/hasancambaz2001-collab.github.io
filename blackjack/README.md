# Blackjack: Test Sonuçları + Canlı Danışman

Bu klasörde üç parça var:

| Dosya | Ne yapar |
|---|---|
| `engine.js` | Kalan deste kompozisyonuna göre **birebir EV** hesaplayan motor: krupiye sonuç olasılıkları, stand/hit/double/split/surrender EV'leri, sigorta EV'si, kurallardan temel strateji üretimi, Hi-Lo sayım. |
| `sim.js` | Monte Carlo simülatörü (tüm CPU çekirdekleri). Her senaryo **40 milyon round**. Sonuçları `results.json`, `results.js` ve `calibration.js` dosyalarına yazar. |
| `index.html` | **Canlı danışman.** Masada gördüğün kartları gir; anlık en iyi hamleyi, true count'u, avantajını ve önerilen bahsi gösterir. |

Çalıştırma:

```bash
node sim.js                 # tüm testler (4 çekirdekte ~4 dk)
node sim.js --rounds 2e6    # hızlı deneme
# index.html'i tarayıcıda aç (çift tıkla), ya da: python3 -m http.server → http://localhost:8000/blackjack/
```

---

## 1. Testlerle bulunan oranlar (40M round / senaryo)

Tipik canlı masa: 8 deste, krupiye soft 17'de durur (S17), split sonrası double serbest (DAS), bir kez split, teslim yok, BJ 3:2, deste yarısında karıştırılıyor (%50 penetrasyon).

| Senaryo | Oyuncu avantajı (bahis başına) | ±95% | Not |
|---|---:|---:|---|
| Temel strateji, düz bahis (tipik canlı masa) | **−0.52%** | 0.04 | Matematiksel olarak en iyi oyun bile kaybeder |
| Krupiye soft 17'de çeker (H17) | −0.71% | 0.04 | H17 masalar ≈0.2% daha kötü |
| **Blackjack 6:5 öder** | **−1.87%** | 0.04 | 3,5 kat daha kötü. **Asla oynama** |
| ENHC (krupiye BJ'ye bakmaz, double/split de kaybedilir) | −0.62% | 0.04 | |
| 6 deste + surrender (iyi kurallar) | −0.44% | 0.04 | |
| Hi-Lo sayım, 1–8 bahis, **her eli oyna**, %50 pen. | −0.31% | 0.04 | %50 penetrasyonda sayım **tek başına yetmiyor** |
| Hi-Lo sayım, 1–16 bahis, her eli oyna, %50 pen. | −0.05% | 0.05 | Başa baş bile değil |
| Hi-Lo sayım, 1–8, her eli oyna, %75 pen. | +0.20% | 0.05 | Kara-kumarhane referansı |
| **Wonging**: sadece TC ≥ +1 iken oyna, %50 pen. | **+0.88%** | 0.11 | Ellerin sadece %16'sında bahis var |
| **Wonging**: sadece TC ≥ +1 iken oyna, %75 pen. | **+1.55%** | 0.10 | Ellerin %21'inde bahis var |
| Martingale (kayıpta ikiye katla) | −0.50% | 0.07 | Aşağıya bak |

### True count'a göre beklenen değer (düz bahis, 8 deste)

| TC | ≤ −2 | −1 | 0 | +1 | +2 | +3 | +4 | +5 |
|---|---|---|---|---|---|---|---|---|
| Avantaj | −1.2% ve altı | −0.79% | −0.28% | **+0.16%** | **+0.72%** | **+1.09%** | **+1.84%** | **+2.06%** |
| Ellerin % kaçı | ~19% | 25.8% | 36.7% | 11.7% | 4.4% | 1.5% | 0.5% | 0.1% |

Kalibrasyon: her +1 TC ≈ **+0.49%** avantaj. Kasa avantajı ancak **TC ≈ +1** civarında tersine dönüyor, ve 8 deste %50 penetrasyonda ellerin sadece ~%18'i TC ≥ +1.

### Martingale efsanesi (100 birim kasa, hedef +20, masa limiti 64)

- Seansların **%81.5'i** +20 hedefe ulaşıyor (ortalama +22.8 birim). İnsanları kandıran kısım bu.
- Seansların **%18.5'i** batıyor (ortalama −103.9 birim).
- Net: **seans başına −0.65 birim.** Bu, kasa avantajının toplam oynanan paraya uygulanmış hali. Bahis sistemi EV'yi değiştirmez, sadece kayıp dağılımının şeklini değiştirir.

## 2. Blackjack'te en iyi nasıl kazanılır? (Öncelik sırasıyla)

1. **Masa seçimi en büyük kaldıraç.** 6:5 masa ~1.4% kaybettirir. 3:2, S17, DAS ara. Masanın (i) panelindeki kuralları danışmanın "Masa kuralları" sekmesine gir.
2. **Kusursuz temel strateji.** Kaybı −2/−3%'ten (sezgisel oyun) −0.5%'e indirir. Bu tek başına kazandırmaz.
3. **Sayım + wonging.** Canlı online masada pozitif EV'nin tek gerçekçi yolu bu: masayı izle, kartları say, **sadece TC ≥ +1 iken bahis koy**, diğer ellerde otur. Her eli oynayarak saymak %50 penetrasyonda yetmiyor.
4. **Sapmalar (index plays).** Danışman bunları kendiliğinden yapar: kalan desteye göre birebir hesapladığı için "16'ya karşı 10'da dur", "TC ≥ +3 iken sigorta al" gibi kararlar otomatik çıkar.
5. **Bahis boyutu: ½ Kelly.** Avantajın %1 iken kasanın ~%0.4'ü kadar bahis. Fazlası batma riskini patlatır.

## 3. Gerçekçi beklenti (dürüst rakamlar)

Canlı masa saatte ~50 round varsayımıyla:

| Strateji | Birim / saat | N0* | N0'a ulaşma süresi | Batma riski (500 birim kasa) | (1000 birim kasa) |
|---|---:|---:|---:|---:|---:|
| Wonging %50 pen. | **+0.12** | 26.5k oynanan el | **~3.300 saat** | %7.5 | %0.6 |
| Wonging %75 pen. | +0.40 | 9.4k oynanan el | ~890 saat | %5.8 | %0.3 |

\*N0: kârın 1 standart sapmayı geçtiği el sayısı. Bundan önce sonuçların çoğu şanstır.

**Çeviri:** Birim 10 ₺ ve kasa 5.000–10.000 ₺ ise beklenen kazanç saatte **~1 ₺**. Matematiksel edge gerçek ama çok ince; varyans ise devasa. Bu bir para makinesi değil.

## 4. Riskler ve yasal durum

- **Kural doğrulama:** "Infinite Blackjack", "Free Bet", "Power Blackjack" gibi varyantlarda deste sonsuz ya da kurallar farklı. Sayım bu masalarda **işe yaramaz**. Danışman sadece klasik shoe'lu masalar için geçerli.
- **Operatör kuralları:** Çoğu online casino, oyun sırasında yazılım yardımı kullanmayı ve sayım/wonging davranışını şartlarında yasaklar. Tespit edilirse hesap kapatılabilir ve **kazanç el konulabilir**. Bahis yayılımı (1→8) ve sadece yüksek sayımda oturma, izlenen davranış kalıplarıdır.
- **Yasal durum:** Türkiye'de lisanssız online casino yasa dışıdır (7258 sayılı Kanun, TCK 228). Kendi bulunduğun yerin mevzuatını kontrol et.
- **Varyans:** +%0.9 edge ile bile 1.000 elde %40+ ihtimalle zarardasın. Kaybetmeyi göze alamayacağın parayla oynama.

## 5. Model notları

- EV hesabı: krupiye sonuçları kalan desteden birebir (peek koşullu). Oyuncunun çektiği kartlar desteden düşülür. Krupiye dağılımı karar anındaki desteye göre sabit tutulur (bilinen, çok küçük bir yaklaşım). Split EV'si iki bağımsız el olarak hesaplanır (resplit yok).
- Üretilen temel strateji, standart 8 deste S17 DAS tablosuyla tek bir sınır durum dışında aynı (A,2'ye karşı 5: double/hit farkı < %0.1 EV).
- Simülasyon: masada 3 başka oyuncu, sayım her round sonunda açılan kartlarla güncellenir, TC = floor(RC / kalan deste), Illustrious 18 + Fab 4 sapmaları.
