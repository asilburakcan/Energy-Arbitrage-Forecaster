

import os
import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

from entsoe import EntsoePandasClient

ENTSOE_KEY = os.getenv("ENTSOE_API_KEY")
client_entsoe = EntsoePandasClient(api_key=ENTSOE_KEY)

COUNTRY_CODES = {
    "DE": "DE_LU",
    "FR": "FR",
    "NL": "NL",
    "BE": "BE",
    "AT": "AT",
}


COUNTRY_COORDS = {
    "DE": [
        {"lat": 52.5, "lon": 13.4},   # Berlin
        {"lat": 53.6, "lon": 10.0},   # Hamburg
        {"lat": 48.1, "lon": 11.6},   # Munich
        {"lat": 50.1, "lon": 8.7},    # Frankfurt
    ],
    "FR": [
        {"lat": 48.9, "lon": 2.3},    # Paris
        {"lat": 45.7, "lon": 4.8},    # Lyon
        {"lat": 43.3, "lon": 5.4},    # Marseille
    ],
    "NL": [
        {"lat": 52.4, "lon": 4.9},    # Amsterdam
        {"lat": 51.9, "lon": 4.5},    # Rotterdam
    ],
    "BE": [
        {"lat": 50.8, "lon": 4.4},    # Brussels
    ],
    "AT": [
        {"lat": 48.2, "lon": 16.4},   # Vienna
        {"lat": 47.1, "lon": 11.4},   # Innsbruck
    ],
}




def fetch_weather(country: str, days_back: int = 30) -> pd.DataFrame:
    """
    Fetches hourly weather for all representative points in a country
    and returns the country-level average as a DataFrame indexed by UTC hour.
    Variables: temperature_2m, wind_speed_10m, wind_gusts_10m,
               cloud_cover, shortwave_radiation
    """
    coords = COUNTRY_COORDS.get(country.upper())
    if not coords:
        print(f"  No weather coords for {country}, skipping.")
        return pd.DataFrame()

    end_dt   = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days_back)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str   = end_dt.strftime("%Y-%m-%d")

    vars_param = "temperature_2m,wind_speed_10m,wind_gusts_10m,cloud_cover,shortwave_radiation"
    all_dfs = []

    for coord in coords:
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude":   coord["lat"],
            "longitude":  coord["lon"],
            "start_date": start_str,
            "end_date":   end_str,
            "hourly":     vars_param,
            "timezone":   "UTC",
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()["hourly"]
            df_loc = pd.DataFrame(data)
            df_loc["time"] = pd.to_datetime(df_loc["time"], utc=True)
            df_loc = df_loc.set_index("time")
            all_dfs.append(df_loc)
        except Exception as e:
            print(f"  Weather fetch failed for {coord}: {e}")

    if not all_dfs:
        return pd.DataFrame()

 
    avg = pd.concat(all_dfs).groupby(level=0).mean()
    avg.columns = [f"wx_{c}" for c in avg.columns]
    return avg


def fetch_weather_forecast(country: str, hours_ahead: int = 48) -> pd.DataFrame:
    """
    Fetches hourly weather forecast from Open-Meteo (free forecast API).
    Returns country-average for the next `hours_ahead` hours.
    """
    coords = COUNTRY_COORDS.get(country.upper())
    if not coords:
        return pd.DataFrame()

    vars_param = "temperature_2m,wind_speed_10m,wind_gusts_10m,cloud_cover,shortwave_radiation"
    all_dfs = []

    for coord in coords:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude":       coord["lat"],
            "longitude":      coord["lon"],
            "hourly":         vars_param,
            "timezone":       "UTC",
            "forecast_days":  max(2, hours_ahead // 24 + 1),
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()["hourly"]
            df_loc = pd.DataFrame(data)
            df_loc["time"] = pd.to_datetime(df_loc["time"], utc=True)
            df_loc = df_loc.set_index("time")
            now = pd.Timestamp.now(tz="UTC")
            df_loc = df_loc[df_loc.index >= now - pd.Timedelta(hours=3)]
            df_loc = df_loc.head(hours_ahead + 3)
            all_dfs.append(df_loc)
        except Exception as e:
            print(f"  Forecast fetch failed for {coord}: {e}")

    if not all_dfs:
        return pd.DataFrame()

    avg = pd.concat(all_dfs).groupby(level=0).mean()
    avg.columns = [f"wx_{c}" for c in avg.columns]
    return avg

def get_weather_at_timestamp(wx_df, ts):

    if wx_df.empty:
        return None

    nearest_ts = wx_df.index.asof(ts)

    if pd.isna(nearest_ts):
        return None

    return wx_df.loc[nearest_ts]



def fetch_prices(country: str, days_back: int = 30) -> pd.Series:
    code = COUNTRY_CODES.get(country.upper(), country)
    # Fiyatlar önceden açıklandığı için yarının sonuna kadar çekilebilir
    end = (pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=1)).replace(hour=23, minute=0, second=0, microsecond=0)
    start = end - pd.Timedelta(days=days_back)
    return client_entsoe.query_day_ahead_prices(code, start=start, end=end)

def fetch_load(country: str, days_back: int = 30) -> pd.DataFrame:
    code = COUNTRY_CODES.get(country.upper(), country)
    # HATA ÇÖZÜLDÜ: Gerçekleşen yük sadece şu anki saate (now) kadar çekilebilir
    end = pd.Timestamp.now(tz="UTC").floor("h")
    start = end - pd.Timedelta(days=days_back)
    return client_entsoe.query_load(code, start=start, end=end).resample("1h").mean()



def fetch_generation(country: str, days_back: int = 30) -> pd.DataFrame:
    code = COUNTRY_CODES.get(country.upper(), country)
    # HATA ÇÖZÜLDÜ: Gerçekleşen üretim sadece şu anki saate (now) kadar çekilebilir
    end = pd.Timestamp.now(tz="UTC").floor("h")
    start = end - pd.Timedelta(days=days_back)
    return client_entsoe.query_generation(code, start=start, end=end).resample("1h").mean()


def build_features(df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    df = df.copy()
    s = df[target_col]


    df["hour_sin"]   = np.sin(2 * np.pi * df.index.hour / 24)
    df["hour_cos"]   = np.cos(2 * np.pi * df.index.hour / 24)
    df["day_sin"]    = np.sin(2 * np.pi * df.index.dayofweek / 7)
    df["day_cos"]    = np.cos(2 * np.pi * df.index.dayofweek / 7)
    df["month_sin"]  = np.sin(2 * np.pi * df.index.month / 12)
    df["month_cos"]  = np.cos(2 * np.pi * df.index.month / 12)
    df["is_weekend"] = (df.index.dayofweek >= 5).astype(int)


    for lag in [1, 24, 48, 168]:
        df[f"price_lag_{lag}"] = s.shift(lag)


    for window in [24, 168]:
        shifted = s.shift(1)
        df[f"price_rolling_mean_{window}"] = shifted.rolling(window).mean()
        df[f"price_rolling_std_{window}"]  = shifted.rolling(window).std()
        df[f"price_rolling_max_{window}"]  = shifted.rolling(window).max()
        df[f"price_rolling_min_{window}"]  = shifted.rolling(window).min()
        df[f"price_range_{window}"]        = (
            df[f"price_rolling_max_{window}"] - df[f"price_rolling_min_{window}"]
        )

    df["price_momentum"]  = s.shift(1) - s.shift(24)
    df["price_zscore_24"] = (
        (s.shift(1) - df["price_rolling_mean_24"]) / (df["price_rolling_std_24"] + 1e-8)
    )

  
    wx_cols = [c for c in df.columns if c.startswith("wx_")]
    for col in wx_cols:
        df[f"{col}_lag1"] = df[col].shift(1)
        df[f"{col}_lag3"] = df[col].shift(3)


    if "wx_temperature_2m" in df.columns:
        t = df["wx_temperature_2m"]
        df["heating_degree"] = (18 - t).clip(lower=0)
        df["cooling_degree"] = (t - 22).clip(lower=0)

    df = df.dropna()
    return df




from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from lightgbm import LGBMRegressor, early_stopping, log_evaluation
from sklearn.model_selection import TimeSeriesSplit


def train_model(df: pd.DataFrame, target_col: str):

    df = build_features(df, target_col)

    X = df.drop(columns=[target_col])
    y = df[target_col]

    # -------------------------------------------------
    # 1. CHRONOLOGICAL SPLIT (NO SHUFFLE, NO RANDOM)
    # -------------------------------------------------
    train_size = int(len(df) * 0.7)
    val_size   = int(len(df) * 0.15)

    X_train = X.iloc[:train_size]
    y_train = y.iloc[:train_size]

    X_val = X.iloc[train_size:train_size + val_size]
    y_val = y.iloc[train_size:train_size + val_size]

    X_test = X.iloc[train_size + val_size:]
    y_test = y.iloc[train_size + val_size:]

    # -------------------------------------------------
    # 2. MODEL TRAINING (VALIDATION CONTROLLED)
    # -------------------------------------------------
    model = LGBMRegressor(
        n_estimators=2000,
        learning_rate=0.03,
        num_leaves=63,
        random_state=42
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        eval_metric="rmse",
        callbacks=[early_stopping(50), log_evaluation(100)]
    )

    # -------------------------------------------------
    # 3. FINAL TEST EVALUATION (ONLY TRUTH)
    # -------------------------------------------------
    y_pred = model.predict(X_test)

    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae  = mean_absolute_error(y_test, y_pred)
    r2   = r2_score(y_test, y_pred)

    print(f"\nTEST RESULTS")
    print(f"RMSE: {rmse:.2f} | MAE: {mae:.2f} | R²: {r2:.3f}")

    # -------------------------------------------------
    # 4. OPTIONAL: LIGHTWEIGHT CV (TRAIN ONLY, NO TEST LEAKAGE)
    # -------------------------------------------------
    tscv = TimeSeriesSplit(n_splits=5)

    cv_scores = []

    for tr_idx, val_idx in tscv.split(X_train):

        m = LGBMRegressor(
            n_estimators=500,
            learning_rate=0.05,
            num_leaves=63,
            random_state=42,
            verbose = -1
        )

        m.fit(X_train.iloc[tr_idx], y_train.iloc[tr_idx])

        preds = m.predict(X_train.iloc[val_idx])
        cv_scores.append(r2_score(y_train.iloc[val_idx], preds))

    print(f"\nCV RESULTS (TRAIN ONLY)")
    print(f"CV R² mean: {np.mean(cv_scores):.3f}")

    # -------------------------------------------------
    # 5. FEATURE IMPORTANCE (UNCHANGED)
    # -------------------------------------------------
    feat_imp = pd.Series(model.feature_importances_, index=X.columns)
    top10 = feat_imp.nlargest(10)

    print("\nTop 10 features:")
    for feat, imp in top10.items():
        print(f"{feat:<40} {imp:.0f}")

    return model, X_test, y_test, y_pred

import matplotlib.pyplot as plt

def predict_future(
    df_history: pd.DataFrame,
    model,
    target_col: str,
    country: str,
    hours_ahead: int = 24,
):
    df_feat = df_history.copy()
    s = df_feat[target_col]

    df_feat["hour_sin"]   = np.sin(2 * np.pi * df_feat.index.hour / 24)
    df_feat["hour_cos"]   = np.cos(2 * np.pi * df_feat.index.hour / 24)
    df_feat["day_sin"]    = np.sin(2 * np.pi * df_feat.index.dayofweek / 7)
    df_feat["day_cos"]    = np.cos(2 * np.pi * df_feat.index.dayofweek / 7)
    df_feat["month_sin"]  = np.sin(2 * np.pi * df_feat.index.month / 12)
    df_feat["month_cos"]  = np.cos(2 * np.pi * df_feat.index.month / 12)
    df_feat["is_weekend"] = (df_feat.index.dayofweek >= 5).astype(int)

    for lag in [24, 48, 168]:
        df_feat[f"price_lag_{lag}"] = s.shift(lag)

    for window in [24, 168]:
        shifted = s.shift(1)
        df_feat[f"price_rolling_mean_{window}"] = shifted.rolling(window).mean()
        df_feat[f"price_rolling_std_{window}"]  = shifted.rolling(window).std()
        df_feat[f"price_rolling_max_{window}"]  = shifted.rolling(window).max()
        df_feat[f"price_rolling_min_{window}"]  = shifted.rolling(window).min()
        df_feat[f"price_range_{window}"]        = (
            df_feat[f"price_rolling_max_{window}"] - df_feat[f"price_rolling_min_{window}"]
        )

    df_feat["price_momentum"]  = s.shift(1) - s.shift(24)
    df_feat["price_zscore_24"] = (
        (s.shift(1) - df_feat["price_rolling_mean_24"]) / (df_feat["price_rolling_std_24"] + 1e-8)
    )

    last = df_feat.dropna().iloc[[-1]]

    now = pd.Timestamp.now(tz="UTC").floor("h")
    future_index = pd.date_range(
        start=now + pd.Timedelta(hours=1), periods=hours_ahead, freq="h", tz="UTC"
    )

    wx_fc = fetch_weather_forecast(country, hours_ahead)
    if not wx_fc.empty:
        print(f"  Weather forecast added for {hours_ahead}h ahead.")
        print(wx_fc.index[:10])

    model_cols = model.feature_name_
    last_known_price = df_history[target_col].iloc[-1]
    predicted_prices = []

    for i, ts in enumerate(future_index):
        row = last.copy()
        row.index = [ts]
        row["hour_sin"]   = np.sin(2 * np.pi * ts.hour / 24)
        row["hour_cos"]   = np.cos(2 * np.pi * ts.hour / 24)
        row["day_sin"]    = np.sin(2 * np.pi * ts.dayofweek / 7)
        row["day_cos"]    = np.cos(2 * np.pi * ts.dayofweek / 7)
        row["month_sin"]  = np.sin(2 * np.pi * ts.month / 12)
        row["month_cos"]  = np.cos(2 * np.pi * ts.month / 12)
        row["is_weekend"] = int(ts.dayofweek >= 5)
        row["price_lag_1"] = last_known_price if i == 0 else predicted_prices[-1]

        if not wx_fc.empty:

            for col in wx_fc.columns:

                if ts in wx_fc.index:
                    row[col] = wx_fc.loc[ts, col]

                lag1_ts = ts - pd.Timedelta(hours=1)
                lag3_ts = ts - pd.Timedelta(hours=3)

                if lag1_ts in wx_fc.index:
                    row[f"{col}_lag1"] = wx_fc.loc[lag1_ts, col]

                if lag3_ts in wx_fc.index:
                    row[f"{col}_lag3"] = wx_fc.loc[lag3_ts, col]

                if "wx_temperature_2m" in row.columns:

                    t = row["wx_temperature_2m"].iloc[0]

                    row["heating_degree"] = max(0, 18 - t)
                    row["cooling_degree"] = max(0, t - 22)

        missing = [c for c in model_cols if c not in row.columns]
        if missing:
            raise ValueError(f"Missing features: {missing}")
        row_df = row[model_cols]
        pred = model.predict(row_df)[0]
        predicted_prices.append(pred)
    preds = np.array(predicted_prices)

    result = pd.DataFrame({
        "predicted_price_eur_mwh": preds.round(2),
    }, index=future_index)

    print(f"\n  {hours_ahead}h Price Forecast for {country}:")
    print(result.to_string())
    return result
    

def arbitrage_signal(
    country_a: str,
    country_b: str,
    days_back: int = 7,
    threshold: float = 5.0,
    spike_pct: float = 20.0,
):
    print(f"\nFetching prices: {country_a} vs {country_b}...")
    prices_a = fetch_prices(country_a, days_back).resample("1h").mean()
    prices_b = fetch_prices(country_b, days_back).resample("1h").mean()

    df = pd.DataFrame({"price_a": prices_a, "price_b": prices_b}).dropna()

    load_a = fetch_load(country_a, days_back)
    load_b = fetch_load(country_b, days_back)

    gen_a = fetch_generation(country_a, days_back)
    gen_b = fetch_generation(country_b, days_back)

    df["spread"]      = df["price_a"] - df["price_b"]
    df["pct_change_a"] = df["price_a"].pct_change().abs() * 100
    df["pct_change_b"] = df["price_b"].pct_change().abs() * 100

    df["load_a"] = load_a.iloc[:, 0].reindex(df.index, method="ffill")
    df["load_b"] = load_b.iloc[:, 0].reindex(df.index, method="ffill")

    def add_generation_feature(df, gen_df, source_col, target_col):
            if source_col not in gen_df.columns:
                return

            x = gen_df[source_col]

            if isinstance(x, pd.DataFrame):
                x = x.sum(axis=1)

            df[target_col] = x.reindex(df.index, method="ffill")


    add_generation_feature(df, gen_a, "Solar", "solar_a")
    add_generation_feature(df, gen_a, "Wind Onshore", "wind_onshore_a")
    add_generation_feature(df, gen_a, "Wind Offshore", "wind_offshore_a")
    
    add_generation_feature(df, gen_b, "Solar", "solar_b")
    add_generation_feature(df, gen_b, "Wind Onshore", "wind_onshore_b")
    add_generation_feature(df, gen_b, "Wind Offshore", "wind_offshore_b")

    has_flow = False
    try:
        for ca, cb in [(country_a, country_b), (country_b, country_a)]:
            flow = client_entsoe.query_crossborder_flows(
                COUNTRY_CODES.get(ca, ca),
                COUNTRY_CODES.get(cb, cb),
                start=pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days_back),
                end=pd.Timestamp.now(tz="UTC").floor("h"),
            ).resample("1h").mean()
            key = "flow_ab" if ca == country_a else "flow_ba"
            df[key] = flow.reindex(df.index, method="ffill")
        has_flow = True
    except Exception as e:
        print(f"  Flow data unavailable ({e})")

    print("  Fetching weather forecasts for spread context...")
    wx_a = fetch_weather_forecast(country_a, hours_ahead=24)
    wx_b = fetch_weather_forecast(country_b, hours_ahead=24)
    if not wx_a.empty and not wx_b.empty:
        common_idx = wx_a.index.intersection(wx_b.index)
        temp_diff = (
            wx_a.loc[common_idx, "wx_temperature_2m"]
            - wx_b.loc[common_idx, "wx_temperature_2m"]
        ) if "wx_temperature_2m" in wx_a.columns else None
        wind_diff = (
            wx_a.loc[common_idx, "wx_wind_speed_10m"]
            - wx_b.loc[common_idx, "wx_wind_speed_10m"]
        ) if "wx_wind_speed_10m" in wx_a.columns else None

        print(f"\n  Weather forecast (next 6h avg):")
        if temp_diff is not None:
            print(f"    Temp diff  ({country_a}-{country_b}): {temp_diff.head(6).mean():.1f} °C")
        if wind_diff is not None:
            print(f"    Wind diff  ({country_a}-{country_b}): {wind_diff.head(6).mean():.1f} km/h")
            if wind_diff.head(6).mean() > 5:
                print(f"     Higher wind in {country_a} → potential price drop → spread may narrow")
            elif wind_diff.head(6).mean() < -5:
                print(f"     Higher wind in {country_b} → potential price drop → spread may widen")

    def signal_row(row):
        if row["spread"] > threshold:
            return f"BUY_{country_b}_SELL_{country_a}"
        elif row["spread"] < -threshold:
            return f"BUY_{country_a}_SELL_{country_b}"
        return "NEUTRAL"

    df["signal"] = df.apply(signal_row, axis=1)

    cols = ["price_a", "price_b", "spread", "signal"]
    if has_flow:
        cols += ["flow_ab", "flow_ba"]
    active = df.tail(10)
    print(f"\n  Last signals (threshold={threshold} €/MWh):")
    print(active[cols].to_string())

    spikes = df[(abs(df["pct_change_a"]) > spike_pct) | (abs(df["pct_change_b"]) > spike_pct)].tail(5)
    if not spikes.empty:
        print(f"\n  ⚠ Price spike(s) detected (>{spike_pct}% hourly change) — asking LLM...")
        for ts, row in spikes.iterrows():
            if abs(row["pct_change_a"]) >= abs(row["pct_change_b"]):
                spiked_country = country_a
                spiked_price = row["price_a"]
                spiked_pct = row["pct_change_a"]
            else:
                spiked_country = country_b
                spiked_price = row["price_b"]
                spiked_pct = row["pct_change_b"]
            
            # Ülkeye göre asıl pazar yük ve üretim verileri (MW)
            if spiked_country == country_a:
                load_actual = row.get("load_a")
                generation_solar = row.get("solar_a")  # İsmini değiştirdik çakışmasın diye
                wind_onshore = row.get("wind_onshore_a")
                wind_offshore = row.get("wind_offshore_a")
            else:
                load_actual = row.get("load_b")
                generation_solar = row.get("solar_b")  # İsmini değiştirdik çakışmasın diye
                wind_onshore = row.get("wind_onshore_b")
                wind_offshore = row.get("wind_offshore_b")
            
            price_spread = row["spread"]
            flow_ab = row.get("flow_ab", None)
            flow_ba = row.get("flow_ba", None)  
            trading_signal = row.get("signal", "NEUTRAL")
    
            rag  = get_rag_context(f"electricity price spike {spiked_country} volatility demand supply imbalance")
            news = get_news_context(spiked_country, max_articles=5, days_back=days_back)
            historical_wx_context = ""
            forecast_wx_context = ""
            
            try:
                wx_history_df = fetch_weather(spiked_country, days_back)
                wx_forecast_df = fetch_weather_forecast(spiked_country, hours_ahead=48)

                if (not wx_history_df.empty and ts <= wx_history_df.index.max()):
                    wx_hist = get_weather_at_timestamp(wx_history_df, ts)
                else:
                    wx_hist = get_weather_at_timestamp(wx_forecast_df, ts)
                    temp = wx_hist["wx_temperature_2m"]
                    wind = wx_hist["wx_wind_speed_10m"]
                    cloud = wx_hist["wx_cloud_cover"]
                    wx_solar_rad = wx_hist["wx_shortwave_radiation"] # İsmini değiştirdik
                    
                    weather_signals = []
                    if temp > 30:
                        weather_signals.append("High temperature may increase cooling demand.")
                    if wind < 10:
                        weather_signals.append("Low wind speed may reduce wind generation.")
                    if wx_solar_rad < 50 and ts.hour in [8, 9, 10, 11, 12, 13, 14, 15, 16]:
                        weather_signals.append("Very low solar radiation during daylight hours may reduce solar generation.")
                    if cloud > 80:
                        weather_signals.append("Heavy cloud cover may suppress solar output.")
    
                    historical_wx_context = f"""
                    Historical weather at spike timestamp:
                    - Temperature: {temp:.1f} °C
                    - Wind speed: {wind:.1f} km/h
                    - Cloud cover: {cloud:.1f} %
                    - Solar radiation: {wx_solar_rad:.1f} W/m²
                    Weather-driven signals:
                    {chr(10).join(f"- {s}" for s in weather_signals)}
                    """
                
                wx_fc = fetch_weather_forecast(spiked_country, hours_ahead=24)
                if not wx_fc.empty:
                    fc_temp = wx_fc["wx_temperature_2m"].head(24).mean()
                    fc_wind = wx_fc["wx_wind_speed_10m"].head(24).mean()
                    fc_cloud = wx_fc["wx_cloud_cover"].head(24).mean()
                    fc_solar = wx_fc["wx_shortwave_radiation"].head(24).mean()
                    
                    forecast_signals = []
                    if fc_temp > 30:
                        forecast_signals.append("Cooling demand likely to remain elevated.")
                    if fc_wind < 10:
                        forecast_signals.append("Wind generation may stay weak.")
                    if fc_solar < 100:
                        forecast_signals.append("Solar generation outlook remains weak.")
    
                    forecast_wx_context = f"""
                    Forecast weather (next 24h average):
                    - Temperature: {fc_temp:.1f} °C
                    - Wind speed: {fc_wind:.1f} km/h
                    - Cloud cover: {fc_cloud:.1f} %
                    - Solar radiation: {fc_solar:.1f} W/m²
                    Forward-looking signals:
                    {chr(10).join(f"- {s}" for s in forecast_signals)}
                    """
            except Exception as e:
                historical_wx_context = f"Weather unavailable: {e}"
    
            market_context = f"""
            Cross-border arbitrage context:
            Country A: {country_a} (Price: {row["price_a"]:.2f} €/MWh)
            Country B: {country_b} (Price: {row["price_b"]:.2f} €/MWh)
            Spread (A-B): {price_spread:.2f} €/MWh
            Current arbitrage signal from system: {trading_signal}
            Cross-border flows:
            {country_a} -> {country_b}: {flow_ab} MW
            {country_b} -> {country_a}: {flow_ba} MW
    
            Mathematical Rules for Spread Interpretation:
            - If Spread is POSITIVE (> 0): Country A is more expensive. Country B is cheaper.
            - If Spread is NEGATIVE (< 0): Country B is more expensive. Country A is cheaper.
            """
    
            prompt = f"""
    You are an expert European Power Market Analyst. Analyze this electricity price spike.
    
    Spiked Country: {spiked_country}
    Timestamp: {ts}
    Spike Price: {spiked_price:.1f} €/MWh (Hourly change: {spiked_pct:.1f}%)
    
    [ACTUAL MARKET DATA AT TIMESTAMPS]
    - Grid Load: {load_actual} MW
    - Solar Generation: {generation_solar} MW
    - Onshore Wind: {wind_onshore} MW
    - Offshore Wind: {wind_offshore} MW
    
    {market_context}
    {historical_wx_context}
    {forecast_wx_context}
    
    Market reports context:
    {rag}
    
    Recent news:
    {news}
    
    STRICT TRADING RULES FOR YOUR RESPONSE:
    1. SIGNAL IS LAW: If the 'Current arbitrage signal from system' is "NEUTRAL", you MUST explicitly state "Trade Direction: NO TRADE RECOMMENDED". Do not suggest any BUY or SELL actions if the signal is NEUTRAL.
    2. DO NOT INVENT DIRECTION: Only recommend a trade if the signal is actively BUY_DE_SELL_FR or BUY_FR_SELL_DE. Match the signal exactly.
    3. PHYSICAL LOGIC: Less solar radiation/cloudy weather ALWAYS means LESS solar generation. Do not state that decreasing solar reduces market pressure.
    4. If Solar Generation > 10000 MW, do not describe solar generation as weak or reduced.
    5. If signal is NEUTRAL, do not discuss arbitrage opportunity. Only explain why spread is below threshold.
    6. Do not claim that trading activity itself will solve or reduce the price spike.
    7. Do not claim that trading activity,
       cross-border trading,
       or arbitrage itself will reduce,
       solve, alleviate,
       normalize or mitigate prices.
    8. SIGNAL DEFINITIONS:
       - "BUY_{country_a}_SELL_{country_b}" means {country_a} is the CHEAPER market and {country_b} is the EXPENSIVE market.
       - "BUY_{country_b}_SELL_{country_a}" means {country_b} is the CHEAPER market and {country_a} is the EXPENSIVE market.
    9. FLOW DEFINITIONS:
       - flow_ab represents physical electricity flow from {country_a} to {country_b}. If high, {country_a} is exporting to {country_b}.
       - flow_ba represents physical electricity flow from {country_b} to {country_a}. If high, {country_b} is exporting to {country_a}.
    

    Answer strictly in 5-7 concise sentences addressing:
    1. Main cause of the spike (using grid load, weather and renewable generation data).
    2. Market persistence over next 24h based on forecast.
    3. Arbitrage impact (explain the spread value logically) and final Trade Direction matching the system signal exactly.

    
    """
            movement_type = (
                                "spike"
                                if spiked_pct > 0
                                else "drop"
                            )

            ts_tr = ts.tz_convert("Europe/Istanbul")
            print(f"\n  [{ts_tr.strftime('%Y-%m-%d %H:%M:%S')}] {spiked_country} {movement_type} {spiked_pct:.1f}%:")

            print(ask_llm(prompt))
    
    return df





import chromadb
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

_rag_ready = False
_collection = None

def load_rag():
    global _rag_ready, _collection
    pdf_paths = [os.getenv(f"PDF_{i}") for i in range(1, 8) if os.getenv(f"PDF_{i}")]
    if not pdf_paths:
        print("  No PDFs found in .env (PDF_1, PDF_2 ...)")
        return
    print(f"  Loading {len(pdf_paths)} PDFs...")
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    all_chunks = []
    for path in pdf_paths:
        loader = PyPDFLoader(path)
        all_chunks.extend(splitter.split_documents(loader.load()))
    ef = DefaultEmbeddingFunction()
    chroma_client = chromadb.Client()
    _collection = chroma_client.create_collection("energy_rag", embedding_function=ef)
    texts = [c.page_content for c in all_chunks]
    _collection.add(documents=texts, ids=[str(i) for i in range(len(texts))])
    _rag_ready = True
    print(f"  {len(all_chunks)} chunks indexed")

def get_rag_context(query: str, n: int = 3) -> str:
    if not _rag_ready:
        load_rag()
    if not _rag_ready:
        return "RAG not loaded."
    results = _collection.query(query_texts=[query], n_results=n)
    return "\n".join(results["documents"][0])



NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
COUNTRY_NEWS_QUERY = {
    "DE": "Germany energy OR electricity OR power grid",
    "FR": "France energy OR electricity OR nuclear power",
    "NL": "Netherlands energy OR electricity OR gas",
    "BE": "Belgium energy OR electricity",
    "AT": "Austria energy OR electricity",
}

def get_news_context(country: str, max_articles: int = 5, days_back: int = 7) -> str:
    if not NEWSAPI_KEY:
        return "No news context (NEWSAPI_KEY not set)."
    query     = COUNTRY_NEWS_QUERY.get(country.upper(), f"{country} energy electricity")
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "language": "en", "sortBy": "publishedAt",
                    "pageSize": max_articles, "from": from_date, "apiKey": NEWSAPI_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
    except Exception as e:
        return f"News fetch failed: {e}"
    if not articles:
        return "No recent news found."
    return "\n".join(
        f"- [{a.get('publishedAt','')[:10]}] ({a.get('source',{}).get('name','')}) {a.get('title','')}"
        for a in articles
    )



from groq import Groq

_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

def ask_llm(prompt: str) -> str:
    response = _groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def llm_market_summary(country: str, days_back: int = 7):
    prices  = fetch_prices(country, days_back)
    latest  = prices.iloc[-1]
    avg, high, low = prices.mean(), prices.max(), prices.min()
    rag  = get_rag_context(f"electricity price drivers {country} renewable energy load balancing")
    news = get_news_context(country)

    wx_fc = fetch_weather_forecast(country, hours_ahead=24)
    wx_str = ""
    if not wx_fc.empty:
        wx_str = f"""
Current weather forecast ({country}, next 24h avg):
  Temperature   : {wx_fc.get('wx_temperature_2m', pd.Series()).mean():.1f} °C
  Wind speed    : {wx_fc.get('wx_wind_speed_10m', pd.Series()).mean():.1f} km/h
  Solar radiation: {wx_fc.get('wx_shortwave_radiation', pd.Series()).mean():.0f} W/m²
  Cloud cover   : {wx_fc.get('wx_cloud_cover', pd.Series()).mean():.0f} %
"""

    prompt = f"""
European electricity market — {country}
Period: last {days_back} days
Latest: {latest:.1f} €/MWh | Avg: {avg:.1f} | High: {high:.1f} | Low: {low:.1f}
{wx_str}
Market context (from reports):
{rag}

Recent news:
{news}

Give a concise market commentary and key price drivers.
"""
    print(ask_llm(prompt))



def main():
    print("\n European Electricity Market CLI")
    print("=" * 40)

    while True:
        # ── Önce ülke ve geçmiş seçimi ──
        country   = input("\nCountry (DE/FR/NL/BE/AT) or q to quit: ").strip().upper()
        if country == "Q":
            break
        days_back = int(input("Days of history (e.g. 60): ").strip())

        print(f"\nFetching {country} data...")
        prices  = fetch_prices(country, days_back)
        load_df = fetch_load(country, days_back)
        gen_df  = fetch_generation(country, days_back)
        print(prices.index[:5])
        print(load_df.index[:5])
        print(gen_df.index[:5])
        
        price_col = f"{COUNTRY_CODES.get(country, country)}_price_day_ahead"
        prices_h = prices.resample("1h").mean()
        load_h = load_df.iloc[:, 0].resample("1h").mean()

        df = pd.DataFrame({price_col: prices_h}).join(
        load_h.rename("load_actual"), how="inner"
        )
        for col, alias in [("Solar", "solar"), ("Wind Onshore", "wind_onshore"), ("Wind Offshore", "wind_offshore")]:
            if col in gen_df.columns:
                df[alias] = gen_df[col].reindex(df.index, method="ffill")


        print("  Fetching weather data (Open-Meteo)...")
        wx = fetch_weather(country, days_back)
        if not wx.empty:
            df = df.join(wx, how="left")
            df[wx.columns] = df[wx.columns].ffill()
            print(f"  Weather features added: {list(wx.columns)}")
        else:
            print("  Weather data unavailable, continuing without it.")

        df = df.ffill().dropna()
        print(f"  {len(df)} rows ready | {df.shape[1]} columns")

        DROP_COLS = [
            "load_actual",
            "solar",
            "wind_onshore",
            "wind_offshore",
        ]

        df = df.drop(
            columns=[c for c in DROP_COLS if c in df.columns]
        )

        print("\n  Training model...")
        model, X_test, y_test, y_pred = train_model(df, price_col)

        # ── Sonra ne yapmak istediğini sor ──
        while True:
            print("\n1) Future price forecast")
            print("2) Arbitrage signal")
            print("3) LLM market summary")
            print("r) Return (change country/days)")
            print("q) Quit")
            choice = input("\nSelect: ").strip().lower()

            if choice == "q":
                return

            elif choice == "r":
                break

            elif choice == "1":
                hours_ahead = int(input("Hours ahead (e.g. 24): ").strip())
                now = pd.Timestamp.now(tz="UTC").floor("h")
                df_for_forecast = df[df.index <= now]
                predict_future(
                    df_history=df_for_forecast,
                    model=model,
                    target_col=price_col,
                    country=country,
                    hours_ahead=hours_ahead,

                )

            elif choice == "2":
                cb    = input(f"Compare {country} against (e.g. FR): ").strip().upper()
                days  = int(input("Days back (e.g. 7): ").strip())
                thr   = float(input("Spread threshold €/MWh (e.g. 5): ").strip())
                spike = float(input("Spike alert % (e.g. 10): ").strip())
                arbitrage_signal(country, cb, days, thr, spike)

            elif choice == "3":
                days_llm = int(input("Days back (e.g. 7): ").strip())
                llm_market_summary(country, days_llm)

            else:
                print("Invalid choice.")


if __name__ == "__main__":
    main()