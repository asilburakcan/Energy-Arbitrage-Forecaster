# energy-arbitrage-forecaster

A CLI tool for European electricity markets pulls real-time market data, trains a price forecasting model, generates cross-border arbitrage signals, and explains price spikes with LLM-assisted analysis.

**Tech Stack:** LightGBM · ENTSO-E API · Open-Meteo · ChromaDB · RAG · Llama 3.3 · Groq · NewsAPI

---

## What it does

The tool connects to ENTSO-E and fetches day-ahead prices, load, and generation data for five European countries (DE, FR, NL, BE, AT). It enriches this with multi-city weather averaging from Open-Meteo, trains a LightGBM model on the combined dataset, and gives you three modes of analysis from a single CLI session no restart required between them.

You pick a country and a history window at startup. Data is fetched, features are built, the model trains, and then you choose what to run next.

---

## Modes

**1. Future Price Forecast**

Builds a feature set from historical prices, load, solar/wind generation, and weather data all lag-shifted to prevent look-ahead leakage. Forecasts hourly prices up to 48 hours ahead using a recursive approach: `price_lag_1` is updated at each step with the previous prediction, so the forecast propagates forward rather than staying flat. Longer lags (24h, 48h, 168h) remain anchored to historical values.

**2. Arbitrage Signal**

Compares day-ahead prices between two countries and calculates the spread over time. When the spread exceeds your threshold, a trade signal is generated. The tool also pulls physical cross-border flows from ENTSO-E and checks the short-term weather forecast difference between the two countries if one side has significantly more wind, it flags that the spread may narrow.

If a price spike is detected (hourly change exceeding your configured threshold), an LLM analysis is automatically triggered. It fetches news from the past 48 hours, pulls weather data at the exact spike timestamp, retrieves relevant context from your energy market PDFs via RAG, and sends everything to Llama 3.3 to generate an interpretive signal what likely caused the move and what the implied trade direction is. The LLM is bound by strict rules: it cannot recommend a trade if the system signal is NEUTRAL, cannot invent direction, and must ground its reasoning in the actual grid load, generation, and weather data passed in the prompt.

**3. LLM Market Summary**

Fetches recent price statistics for a country, adds a 24-hour weather forecast, queries your PDF library via RAG, and pulls recent headlines. Everything goes into a single prompt and Llama 3.3 returns a concise market commentary.

---

## Features

1. Real-time ENTSO-E data: day-ahead prices, load, generation by source, cross-border physical flows
2. Weather integration via Open-Meteo: multi-city averaging across representative coordinates per country, historical archive + short-term forecast
3. Feature engineering: lag features (1h, 24h, 48h, 168h), rolling mean/std/max/min (24h, 168h), rolling z-score, price momentum, cyclical time encodings (sin/cos), heating and cooling degree days all shifted to avoid look-ahead leakage
4. Recursive forecasting: `price_lag_1` updated at each step with the previous prediction, weather forecast injected per timestamp
5. Cross-border arbitrage with physical flow data and weather differential context
6. Automatic spike detection with LLM-assisted interpretation, grounded in grid load and renewable generation data
7. RAG pipeline: PDF reports chunked at 500 characters with 50-character overlap, embedded and stored in an in-memory ChromaDB collection, top-3 semantic retrieval on each LLM call

---

## Model

LightGBM trained on an 80/20 temporal split with a held-out nested validation set. Cross-validated using TimeSeriesSplit (5 folds) to prevent data leakage. Top features typically include price lags, rolling z-score, solar generation, and weather radiation lag.

**Limitations:** forecast accuracy degrades beyond 24 hours, particularly during demand shocks or unplanned outages not captured in the feature set. Only `price_lag_1` is updated recursively during inference longer lag features stay fixed, which can cause drift over extended horizons. Weather forecast uncertainty also compounds over time. This tool generates analytical signals, not financial recommendations.

---

## RAG System

PDF reports (configured via `.env`) are chunked at 500 characters with 50-character overlap and stored in an in-memory ChromaDB collection using the default embedding function. On each LLM call, a semantic query retrieves the 3 most relevant passages and injects them into the prompt alongside live news and market data.

---

## Installation

```bash
git clone https://github.com/yourusername/energy-arbitrage-forecaster.git
cd energy-arbitrage-forecaster

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your keys:

```
ENTSOE_API_KEY=your_entsoe_api_key_here
GROQ_API_KEY=your_groq_api_key_here
NEWSAPI_KEY=your_newsapi_key_here

# PDF paths for RAG (optional)
PDF_1=/path/to/your/report1.pdf
PDF_2=/path/to/your/report2.pdf
```

ENTSO-E API key: https://transparency.entsoe.eu (free registration)

```bash
python main.py
```

---

## Disclaimer

For educational and research purposes only. Not financial advice.

---

---

# energy-arbitrage-forecaster

Avrupa elektrik piyasaları için gerçek zamanlı veri çekimi, fiyat tahmini, sınır ötesi arbitraj sinyali ve LLM destekli piyasa analizi yapan bir CLI aracı.

**Tech Stack:** LightGBM · ENTSO-E API · Open-Meteo · ChromaDB · RAG · Llama 3.3 · Groq · NewsAPI

---

## Ne yapıyor?

Araç, ENTSO-E üzerinden beş Avrupa ülkesi (DE, FR, NL, BE, AT) için gün öncesi fiyatlar, yük ve üretim verisi çekiyor. Open-Meteo'dan ülke başına çoklu şehir ortalamasıyla hava verisi ekliyor, bu birleşik veri üzerinde LightGBM eğitiyor ve tek bir CLI oturumunda üç farklı analiz modu sunuyor modlar arasında geçişte yeniden başlatmana gerek yok.

Başlangıçta ülke ve geçmiş gün sayısını seçiyorsun. Veri çekilip feature'lar oluşturulunca model eğitiliyor, ardından ne yapmak istediğini seçiyorsun.

---

## Modlar

**1. Gelecek Fiyat Tahmini**

Geçmiş fiyatlar, yük, güneş/rüzgar üretimi ve hava verisinden look-ahead sızıntısını önleyecek şekilde lag-shift uygulanarak feature seti oluşturuluyor. 48 saate kadar saatlik fiyat tahmini üretiyor. Her adımda `price_lag_1`, bir önceki tahminin değeriyle güncelleniyor bu sayede tahminler statik kalmak yerine ileriye gerçekçi şekilde yayılıyor. Daha uzun laglar (24h, 48h, 168h) geçmiş değerlere sabitli kalıyor.

**2. Arbitraj Sinyali**

İki ülke arasındaki gün öncesi fiyatları karşılaştırıyor ve spread'i hesaplıyor. Eşik aşılınca işlem sinyali üretiyor. Ayrıca ENTSO-E'den fiziksel cross-border flow verisi çekiyor ve iki ülke arasındaki kısa vadeli hava tahmin farkını gösteriyor önemli bir rüzgar farkı varsa spread'in daralabileceğini işaretliyor.

Saatlik fiyat değişimi belirlediğin eşiği aşarsa LLM analizi otomatik tetikleniyor: son 48 saatin haberleri çekiliyor, spike anındaki hava verisi alınıyor, PDF'lerden RAG ile bağlam getiriliyor ve hepsi Llama 3.3'e gönderiliyor. LLM katı kurallara bağlı: sistem sinyali NEUTRAL ise işlem öneremiyor, yön uyduramıyor, ve tüm yorumunu prompta geçirilen gerçek şebeke yükü, üretim ve hava verisiyle gerekçelendirmek zorunda.

**3. LLM Piyasa Özeti**

Seçilen ülke için son fiyat istatistiklerini çekiyor, 24 saatlik hava tahmini ekliyor, PDF kütüphanesine RAG sorgusu yapıyor ve son haberleri alıyor. Hepsi tek bir prompta giriyor, Llama 3.3 kısa bir piyasa yorumu döndürüyor.

---

## Özellikler

1. Gerçek zamanlı ENTSO-E verisi: gün öncesi fiyatlar, yük, kaynaklara göre üretim, fiziksel cross-border akışlar
2. Open-Meteo ile hava entegrasyonu: ülke başına çoklu koordinat ortalaması, geçmiş arşiv ve kısa vadeli tahmin
3. Feature engineering: lag feature'lar (1h, 24h, 48h, 168h), rolling mean/std/max/min (24h, 168h), rolling z-score, fiyat momentumu, döngüsel zaman kodlamaları (sin/cos), ısıtma ve soğutma derece günleri tümü look-ahead sızıntısını önlemek için kaydırılmış
4. Rekürsif tahmin: `price_lag_1` her adımda önceki tahminle güncelleniyor, hava tahmini her timestamp için prompta enjekte ediliyor
5. Fiziksel akış verisi ve hava farkı bağlamıyla sınır ötesi arbitraj
6. Otomatik spike tespiti ve şebeke yükü ile yenilenebilir üretim verisine dayalı LLM yorumu
7. RAG pipeline: PDF raporlar 500 karakterlik parçalara bölünüyor (50 karakter örtüşme), bellek içi ChromaDB koleksiyonunda tutuluyor, her LLM çağrısında semantik sorguyla en ilgili 3 pasaj getiriliyor

---

## Model

LightGBM, %80/20 zamansal bölünme ve iç içe validation setiyle eğitiliyor. Veri sızıntısını önlemek için TimeSeriesSplit (5 fold) ile cross-validation yapılıyor. En önemli feature'lar genellikle fiyat lag'ları, rolling z-score, solar üretim ve hava radyasyon lag'ı oluyor.

**Sınırlılıklar:** 24 saatin ötesinde tahmin doğruluğu düşüyor özellikle feature setine yansımayan talep şokları veya plansız arızalarda. Çıkarım sırasında yalnızca `price_lag_1` rekürsif güncelleniyor; daha uzun lag feature'lar sabit kalıyor, bu da uzun ufuklarda sürüklenmeye yol açabiliyor. Hava tahmin belirsizliği de zaman içinde birikuyor. Bu araç analitik sinyal üretiyor, finansal öneri değil.

---

## RAG Sistemi

PDF raporlar (`.env` üzerinden yapılandırılıyor) 500 karakterlik parçalara bölünüyor (50 karakter örtüşme) ve bellek içi bir ChromaDB koleksiyonunda varsayılan embedding fonksiyonuyla tutuluyor. Her LLM çağrısında semantik sorgu en ilgili 3 pasajı getiriyor ve bunlar canlı haberler ile piyasa verisiyle birlikte prompta ekleniyor.

---

## Kurulum

```bash
git clone https://github.com/yourusername/energy-arbitrage-forecaster.git
cd energy-arbitrage-forecaster

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

`.env.example` dosyasını `.env` olarak kopyala ve anahtarlarını gir:

```
ENTSOE_API_KEY=your_entsoe_api_key_here
GROQ_API_KEY=your_groq_api_key_here
NEWSAPI_KEY=your_newsapi_key_here

# RAG için PDF yolları (opsiyonel)
PDF_1=/path/to/your/report1.pdf
PDF_2=/path/to/your/report2.pdf
```

ENTSO-E API anahtarı: https://transparency.entsoe.eu (ücretsiz kayıt)

```bash
python main.py
```

---

## Yasal Uyarı

Yalnızca eğitim ve araştırma amaçlıdır. Finansal tavsiye değildir.
