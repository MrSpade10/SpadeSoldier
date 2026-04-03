# ============================================================
# indicators.py — Teknik Gösterge Hesaplama Motoru
# ============================================================
# PARÇA 2/5 | Versiyon: 1.0
# Tüm Tier 1 + Tier 2 + Tier 3 göstergeleri
# Vektörize pandas/numpy — döngü yok, hızlı
# ============================================================

import pandas as pd
import numpy as np
from typing import Optional

from config import logger


class IndicatorEngine:
    """
    Bir hissenin OHLCV verisinden tüm teknik göstergeleri hesaplar.
    Tek seferde tüm göstergeler eklenir → sonra strateji motoru filtreler.
    """

    def calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Tüm göstergeleri hesapla ve DataFrame'e kolon olarak ekle.
        
        Args:
            df: OHLCV DataFrame (open, high, low, close, volume)
        
        Returns:
            Gösterge kolonları eklenmiş DataFrame
        """
        if df is None or len(df) < 50:
            return df

        df = df.copy()

        # NaN'leri temizle
        df['close'] = df['close'].ffill()
        df['volume'] = df['volume'].fillna(0)

        # ── TIER 1 ──
        df = self._calc_rsi(df)
        df = self._calc_macd(df)
        df = self._calc_volume_ratio(df)
        df = self._calc_sma50(df)

        # ── TIER 2 ──
        df = self._calc_adx(df)
        df = self._calc_sma200(df)
        df = self._calc_ema_cross(df)
        df = self._calc_bollinger(df)

        # ── TIER 3 ──
        df = self._calc_obv(df)
        df = self._calc_vwap(df)
        df = self._calc_recent_performance(df)

        return df

    # ════════════════════════════════════════════════════════
    # TIER 1: Temel Göstergeler
    # ════════════════════════════════════════════════════════

    def _calc_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        RSI (Relative Strength Index)
        0-100 arası. <30 aşırı satım, >70 aşırı alım.
        """
        delta = df['close'].diff()

        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        # Wilder's smoothing (EMA benzeri)
        avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))

        return df

    def _calc_macd(self, df: pd.DataFrame,
                    fast: int = 12, slow: int = 26,
                    signal: int = 9) -> pd.DataFrame:
        """
        MACD (Moving Average Convergence Divergence)
        macd_line: EMA12 - EMA26
        macd_signal: EMA9 of macd_line
        macd_hist: macd_line - macd_signal
        """
        ema_fast = df['close'].ewm(span=fast, min_periods=fast).mean()
        ema_slow = df['close'].ewm(span=slow, min_periods=slow).mean()

        df['macd_line'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd_line'].ewm(
            span=signal, min_periods=signal
        ).mean()
        df['macd_hist'] = df['macd_line'] - df['macd_signal']

        # Önceki günün histogram değeri (turning up tespiti için)
        df['macd_hist_prev'] = df['macd_hist'].shift(1)

        # Crossover tespiti
        # MACD line sinyal çizgisini yukarı kesiyor
        df['macd_cross_up'] = (
            (df['macd_line'] > df['macd_signal']) &
            (df['macd_line'].shift(1) <= df['macd_signal'].shift(1))
        )
        # MACD line sinyal çizgisini aşağı kesiyor
        df['macd_cross_down'] = (
            (df['macd_line'] < df['macd_signal']) &
            (df['macd_line'].shift(1) >= df['macd_signal'].shift(1))
        )

        return df

    def _calc_volume_ratio(self, df: pd.DataFrame,
                            period: int = 20) -> pd.DataFrame:
        """
        Hacim oranı: Günlük hacim / 20 günlük ortalama hacim
        1.5 = ortalamanın %50 üstünde hacim
        """
        vol_avg = df['volume'].rolling(window=period, min_periods=10).mean()
        df['volume_ratio'] = df['volume'] / vol_avg.replace(0, np.nan)

        return df

    def _calc_sma50(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        SMA50 ve fiyatın SMA50'ye göre pozisyonu
        """
        df['sma50'] = df['close'].rolling(window=50, min_periods=40).mean()

        # Fiyat/SMA50 farkı (yüzde olarak)
        df['price_sma50_pct'] = (
            (df['close'] - df['sma50']) / df['sma50'] * 100
        )

        return df

    # ════════════════════════════════════════════════════════
    # TIER 2: Trend ve Volatilite
    # ════════════════════════════════════════════════════════

    def _calc_adx(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        ADX (Average Directional Index)
        Trend gücünü ölçer. >25 güçlü trend.
        """
        high = df['high']
        low = df['low']
        close = df['close']

        # True Range
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # +DM ve -DM
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm = np.where(
            (up_move > down_move) & (up_move > 0), up_move, 0.0
        )
        minus_dm = np.where(
            (down_move > up_move) & (down_move > 0), down_move, 0.0
        )

        plus_dm = pd.Series(plus_dm, index=df.index)
        minus_dm = pd.Series(minus_dm, index=df.index)

        # Wilder's smoothing
        atr = tr.ewm(alpha=1/period, min_periods=period).mean()
        plus_di = 100 * (
            plus_dm.ewm(alpha=1/period, min_periods=period).mean() /
            atr.replace(0, np.nan)
        )
        minus_di = 100 * (
            minus_dm.ewm(alpha=1/period, min_periods=period).mean() /
            atr.replace(0, np.nan)
        )

        # DX ve ADX
        di_sum = plus_di + minus_di
        di_diff = (plus_di - minus_di).abs()
        dx = 100 * (di_diff / di_sum.replace(0, np.nan))

        df['adx'] = dx.ewm(alpha=1/period, min_periods=period).mean()
        df['plus_di'] = plus_di
        df['minus_di'] = minus_di

        return df

    def _calc_sma200(self, df: pd.DataFrame) -> pd.DataFrame:
        """SMA200 ve pozisyon"""
        df['sma200'] = df['close'].rolling(
            window=200, min_periods=150
        ).mean()

        df['price_sma200_pct'] = (
            (df['close'] - df['sma200']) / df['sma200'] * 100
        )

        return df

    def _calc_ema_cross(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        EMA9 / EMA21 cross sistemi
        """
        df['ema9'] = df['close'].ewm(span=9, min_periods=9).mean()
        df['ema21'] = df['close'].ewm(span=21, min_periods=21).mean()

        # Mevcut durum
        df['ema_bullish'] = df['ema9'] > df['ema21']

        # Golden cross: EMA9 EMA21'i yukarı kesti (son 3 gün içinde)
        cross_up = (
            (df['ema9'] > df['ema21']) &
            (df['ema9'].shift(1) <= df['ema21'].shift(1))
        )
        # Son 3 gün içinde golden cross oldu mu
        df['ema_golden_cross'] = (
            cross_up |
            cross_up.shift(1).fillna(False) |
            cross_up.shift(2).fillna(False)
        )

        # Death cross: EMA9 EMA21'i aşağı kesti (son 3 gün içinde)
        cross_down = (
            (df['ema9'] < df['ema21']) &
            (df['ema9'].shift(1) >= df['ema21'].shift(1))
        )
        df['ema_death_cross'] = (
            cross_down |
            cross_down.shift(1).fillna(False) |
            cross_down.shift(2).fillna(False)
        )

        return df

    def _calc_bollinger(self, df: pd.DataFrame,
                         period: int = 20,
                         std_dev: float = 2.0) -> pd.DataFrame:
        """
        Bollinger Bands
        """
        sma = df['close'].rolling(window=period, min_periods=15).mean()
        std = df['close'].rolling(window=period, min_periods=15).std()

        df['bb_upper'] = sma + (std_dev * std)
        df['bb_lower'] = sma - (std_dev * std)
        df['bb_middle'] = sma

        # Bant genişliği (squeeze tespiti için)
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / sma * 100
        bb_width_avg = df['bb_width'].rolling(
            window=50, min_periods=20
        ).mean()

        # Pozisyon: Fiyat bantlar içinde nerede (0-1 arası)
        band_range = (df['bb_upper'] - df['bb_lower']).replace(0, np.nan)
        df['bb_position'] = (df['close'] - df['bb_lower']) / band_range

        # Durumlar
        df['bb_near_lower'] = df['bb_position'] < 0.20
        df['bb_near_upper'] = df['bb_position'] > 0.80
        df['bb_squeeze'] = df['bb_width'] < (bb_width_avg * 0.50)
        df['bb_breakout_up'] = (
            (df['close'] > df['bb_upper']) &
            (df['close'].shift(1) <= df['bb_upper'].shift(1))
        )

        return df

    # ════════════════════════════════════════════════════════
    # TIER 3: Gelişmiş Göstergeler
    # ════════════════════════════════════════════════════════

    def _calc_obv(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        OBV (On Balance Volume)
        Fiyat yönüne göre hacim toplama/çıkarma
        """
        price_change = df['close'].diff()
        signed_volume = np.where(
            price_change > 0, df['volume'],
            np.where(price_change < 0, -df['volume'], 0)
        )
        df['obv'] = pd.Series(signed_volume, index=df.index).cumsum()

        # OBV trend (son 10 günlük lineer regresyon eğimi)
        df['obv_slope'] = self._rolling_slope(df['obv'], window=10)

        # OBV diverjansı: Fiyat düşüyor ama OBV yükseliyor
        price_slope = self._rolling_slope(df['close'], window=10)
        df['obv_divergence_bull'] = (
            (price_slope < 0) & (df['obv_slope'] > 0)
        )

        return df

    def _calc_vwap(self, df: pd.DataFrame,
                    period: int = 20) -> pd.DataFrame:
        """
        Rolling VWAP (Volume Weighted Average Price)
        Günlük veriden hesaplanan yaklaşık VWAP
        """
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        tp_volume = typical_price * df['volume']

        df['vwap'] = (
            tp_volume.rolling(window=period, min_periods=10).sum() /
            df['volume'].rolling(window=period, min_periods=10).sum().replace(
                0, np.nan
            )
        )

        df['price_vs_vwap'] = (
            (df['close'] - df['vwap']) / df['vwap'] * 100
        )

        return df

    def _calc_recent_performance(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Son 20 günlük performans (yüzde değişim)
        """
        df['perf_20d'] = df['close'].pct_change(periods=20)
        df['perf_10d'] = df['close'].pct_change(periods=10)
        df['perf_5d'] = df['close'].pct_change(periods=5)

        return df

    # ════════════════════════════════════════════════════════
    # YARDIMCI FONKSİYONLAR
    # ════════════════════════════════════════════════════════

    @staticmethod
    def _rolling_slope(series: pd.Series, window: int = 10) -> pd.Series:
        """
        Rolling lineer regresyon eğimi.
        Vektörize hesaplama — döngü yok.
        """
        def slope_func(arr):
            if len(arr) < window or np.isnan(arr).any():
                return np.nan
            x = np.arange(len(arr))
            # Basit lineer regresyon eğimi
            x_mean = x.mean()
            y_mean = arr.mean()
            num = ((x - x_mean) * (arr - y_mean)).sum()
            den = ((x - x_mean) ** 2).sum()
            if den == 0:
                return 0.0
            return num / den

        return series.rolling(window=window, min_periods=window).apply(
            slope_func, raw=True
        )


# ════════════════════════════════════════════════════════════
# KOŞUL KONTROL MOTORU
# ════════════════════════════════════════════════════════════

class ConditionChecker:
    """
    Strateji parametrelerini alır, her gün için koşulların
    sağlanıp sağlanmadığını boolean Series olarak döndürür.
    """

    def check_all(self, df: pd.DataFrame,
                   params: dict) -> pd.Series:
        """
        Tüm koşulları kontrol et.
        
        Args:
            df: Göstergeleri hesaplanmış DataFrame
            params: Strateji parametreleri dict
                    ör: {"rsi_range": (40,60), "macd_condition": "histogram_positive", ...}
        
        Returns:
            Boolean Series — True olan günler sinyal günü
        """
        # Başlangıçta tüm günler True (filtreler daraltacak)
        mask = pd.Series(True, index=df.index)

        # ── TIER 1 ──

        # RSI aralığı
        if 'rsi_range' in params and params['rsi_range'] is not None:
            low, high = params['rsi_range']
            mask &= (df['rsi'] >= low) & (df['rsi'] <= high)

        # MACD durumu
        if 'macd_condition' in params and params['macd_condition'] is not None:
            mask &= self._check_macd(df, params['macd_condition'])

        # Hacim çarpanı
        if 'volume_multiplier' in params and params['volume_multiplier'] is not None:
            mask &= df['volume_ratio'] >= params['volume_multiplier']

        # Fiyat vs SMA50
        if 'price_vs_sma50' in params and params['price_vs_sma50'] is not None:
            mask &= self._check_sma_position(
                df, 'price_sma50_pct', params['price_vs_sma50']
            )

        # ── TIER 2 ──

        # ADX eşiği
        if 'adx_threshold' in params and params['adx_threshold'] is not None:
            mask &= df['adx'] >= params['adx_threshold']

        # Fiyat vs SMA200
        if 'price_vs_sma200' in params and params['price_vs_sma200'] is not None:
            mask &= self._check_sma_position(
                df, 'price_sma200_pct', params['price_vs_sma200']
            )

        # EMA cross
        if 'ema_cross' in params and params['ema_cross'] is not None:
            mask &= self._check_ema(df, params['ema_cross'])

        # Bollinger pozisyonu
        if 'bollinger_position' in params and params['bollinger_position'] is not None:
            mask &= self._check_bollinger(df, params['bollinger_position'])

        # ── TIER 3 ──

        # OBV trend
        if 'obv_trend' in params and params['obv_trend'] is not None:
            mask &= self._check_obv(df, params['obv_trend'])

        # VWAP pozisyonu
        if 'vwap_position' in params and params['vwap_position'] is not None:
            mask &= self._check_vwap(df, params['vwap_position'])

        # Son performans
        if 'recent_performance' in params and params['recent_performance'] is not None:
            low, high = params['recent_performance']
            mask &= (df['perf_20d'] >= low) & (df['perf_20d'] <= high)

        # NaN olan günleri False yap
        mask = mask.fillna(False)

        return mask

    # ── Alt kontrol fonksiyonları ──

    def _check_macd(self, df: pd.DataFrame, condition: str) -> pd.Series:
        """MACD koşulu kontrolü"""
        if condition == "histogram_positive":
            return df['macd_hist'] > 0
        elif condition == "histogram_negative":
            return df['macd_hist'] < 0
        elif condition == "histogram_turning_up":
            return df['macd_hist'] > df['macd_hist_prev']
        elif condition == "crossover_up":
            return df['macd_cross_up']
        elif condition == "crossover_down":
            return df['macd_cross_down']
        else:
            return pd.Series(True, index=df.index)

    def _check_sma_position(self, df: pd.DataFrame,
                              pct_col: str,
                              position: str) -> pd.Series:
        """Fiyat vs SMA pozisyon kontrolü"""
        if position == "above":
            return df[pct_col] > 0
        elif position == "below":
            return df[pct_col] < 0
        elif position == "near":
            return df[pct_col].abs() <= 2.0  # %2 içinde
        else:
            return pd.Series(True, index=df.index)

    def _check_ema(self, df: pd.DataFrame,
                    condition: str) -> pd.Series:
        """EMA cross kontrolü"""
        if condition == "bullish":
            return df['ema_bullish']
        elif condition == "bearish":
            return ~df['ema_bullish']
        elif condition == "golden_cross":
            return df['ema_golden_cross']
        elif condition == "death_cross":
            return df['ema_death_cross']
        else:
            return pd.Series(True, index=df.index)

    def _check_bollinger(self, df: pd.DataFrame,
                          condition: str) -> pd.Series:
        """Bollinger Band kontrolü"""
        if condition == "near_lower":
            return df['bb_near_lower']
        elif condition == "near_upper":
            return df['bb_near_upper']
        elif condition == "squeeze":
            return df['bb_squeeze']
        elif condition == "breakout_up":
            return df['bb_breakout_up']
        else:
            return pd.Series(True, index=df.index)

    def _check_obv(self, df: pd.DataFrame,
                    condition: str) -> pd.Series:
        """OBV trend kontrolü"""
        if condition == "rising":
            return df['obv_slope'] > 0
        elif condition == "falling":
            return df['obv_slope'] < 0
        elif condition == "divergence":
            return df['obv_divergence_bull']
        else:
            return pd.Series(True, index=df.index)

    def _check_vwap(self, df: pd.DataFrame,
                     condition: str) -> pd.Series:
        """VWAP pozisyon kontrolü"""
        if condition == "above":
            return df['price_vs_vwap'] > 0
        elif condition == "below":
            return df['price_vs_vwap'] < 0
        else:
            return pd.Series(True, index=df.index)


# ════════════════════════════════════════════════════════════
# TEST
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    from data_loader import DataLoader

    print("=" * 50)
    print("Indicators Test")
    print("=" * 50)

    # Veri yükle
    loader = DataLoader()
    df = loader.get_data("THYAO", max_cache_age=7)
    loader.close()

    if df is None:
        print("❌ Veri yüklenemedi!")
        exit()

    print(f"\n📊 Ham veri: {len(df)} satır")

    # Göstergeleri hesapla
    engine = IndicatorEngine()
    df = engine.calculate_all(df)

    print(f"\n📈 Gösterge kolonları ({len(df.columns)} kolon):")
    for col in sorted(df.columns):
        non_null = df[col].notna().sum()
        print(f"  {col:25s} → {non_null} değer")

    # Son günün göstergeleri
    last = df.iloc[-1]
    print(f"\n📌 THYAO Son Gün Göstergeleri:")
    print(f"  Kapanış:    {last['close']:.2f} TL")
    print(f"  RSI:        {last['rsi']:.1f}")
    print(f"  MACD Hist:  {last['macd_hist']:.4f}")
    print(f"  Hacim Oranı:{last['volume_ratio']:.2f}x")
    print(f"  ADX:        {last['adx']:.1f}")
    print(f"  BB Pozisyon:{last['bb_position']:.2f}")
    print(f"  20g Perf:   %{last['perf_20d']*100:.1f}")

    # Koşul kontrolü test
    checker = ConditionChecker()

    test_params = {
        "rsi_range": (40, 60),
        "macd_condition": "histogram_positive",
        "volume_multiplier": 1.5,
        "price_vs_sma50": "above",
        "adx_threshold": 20,
        "bollinger_position": None,
        "ema_cross": "bullish",
        "obv_trend": None,
        "vwap_position": None,
        "recent_performance": None,
        "price_vs_sma200": None,
    }

    signals = checker.check_all(df, test_params)
    signal_count = signals.sum()

    print(f"\n🔍 Test strateji sinyal sayısı: {signal_count}")
    if signal_count > 0:
        signal_dates = df.index[signals]
        print(f"  İlk sinyal: {signal_dates[0].date()}")
        print(f"  Son sinyal: {signal_dates[-1].date()}")

    print("\n✅ Indicators test tamamlandı!")
