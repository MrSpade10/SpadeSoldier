# ============================================================
# backtester.py — Backtest Motoru
# ============================================================
# PARÇA 3/5 | Versiyon: 1.0
# Strateji parametrelerini alır, tüm hisselerde test eder.
# Forward return hesaplar, train/test split uygular.
# Sektör bazlı korelasyon kontrolü yapar.
# ============================================================

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from config import BACKTEST, SECTOR_MAP, DEFAULT_SECTOR, get_sector, logger
from indicators import IndicatorEngine, ConditionChecker


class SignalResult:
    """Tek bir sinyalin sonucu"""
    __slots__ = [
        'ticker', 'date', 'entry_price', 'sector',
        'ret_5d', 'ret_10d', 'ret_20d',
        'max_gain_5d', 'max_gain_10d', 'max_gain_20d',
        'max_dd_5d', 'max_dd_10d', 'max_dd_20d',
    ]

    def __init__(self, ticker, date, entry_price, sector):
        self.ticker = ticker
        self.date = date
        self.entry_price = entry_price
        self.sector = sector

        # Holding period getirileri
        self.ret_5d = None
        self.ret_10d = None
        self.ret_20d = None

        # Holding period içindeki max kazanç
        self.max_gain_5d = None
        self.max_gain_10d = None
        self.max_gain_20d = None

        # Holding period içindeki max drawdown
        self.max_dd_5d = None
        self.max_dd_10d = None
        self.max_dd_20d = None


class BacktestResult:
    """Bir stratejinin tüm sonuçları"""

    def __init__(self, strategy: dict):
        self.strategy = strategy
        self.signals: List[SignalResult] = []
        self.train_signals: List[SignalResult] = []
        self.test_signals: List[SignalResult] = []

    @property
    def total_signals(self):
        return len(self.signals)

    @property
    def train_count(self):
        return len(self.train_signals)

    @property
    def test_count(self):
        return len(self.test_signals)


class Backtester:
    """
    Ana backtest motoru.
    Strateji + veri → sinyal bul → forward return hesapla
    """

    def __init__(self):
        self.indicator_engine = IndicatorEngine()
        self.condition_checker = ConditionChecker()

        # Göstergeleri hesaplanmış veri cache'i
        # (aynı veriyi her strateji için tekrar hesaplamamak için)
        self._indicator_cache: Dict[str, pd.DataFrame] = {}

    # ────────────────────────────────────────────────────────
    # ANA FONKSİYON
    # ────────────────────────────────────────────────────────

    def run(self, strategy: dict,
            all_data: Dict[str, pd.DataFrame]) -> BacktestResult:
        """
        Bir stratejiyi tüm hisselerde backtest et.

        Args:
            strategy: Parametre dict
            all_data: {ticker: DataFrame} dict

        Returns:
            BacktestResult
        """
        result = BacktestResult(strategy)

        for ticker, raw_df in all_data.items():
            try:
                signals = self._process_ticker(ticker, raw_df, strategy)
                result.signals.extend(signals)
            except Exception as e:
                logger.debug(f"{ticker}: Backtest hatası — {e}")
                continue

        # Train/Test split
        self._split_train_test(result)

        return result

    # ────────────────────────────────────────────────────────
    # HİSSE İŞLEME
    # ────────────────────────────────────────────────────────

    def _process_ticker(self, ticker: str,
                         raw_df: pd.DataFrame,
                         strategy: dict) -> List[SignalResult]:
        """Tek bir hisse için sinyal bul ve forward return hesapla"""

        # Göstergeleri hesapla (cache'den veya yeniden)
        df = self._get_indicators(ticker, raw_df)

        if df is None or len(df) < 50:
            return []

        # Koşulları kontrol et → sinyal günlerini bul
        signal_mask = self.condition_checker.check_all(df, strategy)

        # Sinyal olan günlerin indekslerini al
        signal_indices = np.where(signal_mask.values)[0]

        if len(signal_indices) == 0:
            return []

        # Forward return hesapla
        close_arr = df['close'].values
        high_arr = df['high'].values if 'high' in df.columns else close_arr
        low_arr = df['low'].values if 'low' in df.columns else close_arr
        dates = df.index

        sector = get_sector(ticker)
        signals = []

        for idx in signal_indices:
            # Yeterli forward veri var mı?
            if idx + 20 >= len(df):
                continue

            entry_price = close_arr[idx]
            if entry_price <= 0 or np.isnan(entry_price):
                continue

            sig = SignalResult(
                ticker=ticker,
                date=dates[idx],
                entry_price=entry_price,
                sector=sector,
            )

            # Her holding period için getiri ve min/max hesapla
            for period, attr_ret, attr_gain, attr_dd in [
                (5, 'ret_5d', 'max_gain_5d', 'max_dd_5d'),
                (10, 'ret_10d', 'max_gain_10d', 'max_dd_10d'),
                (20, 'ret_20d', 'max_gain_20d', 'max_dd_20d'),
            ]:
                end_idx = idx + period

                if end_idx >= len(df):
                    continue

                # Kapanış getirisi
                exit_price = close_arr[end_idx]
                ret = (exit_price - entry_price) / entry_price
                setattr(sig, attr_ret, ret)

                # Period içindeki high/low ile max gain ve max drawdown
                period_highs = high_arr[idx + 1: end_idx + 1]
                period_lows = low_arr[idx + 1: end_idx + 1]

                if len(period_highs) > 0:
                    max_price = np.nanmax(period_highs)
                    min_price = np.nanmin(period_lows)

                    max_gain = (max_price - entry_price) / entry_price
                    max_dd = (min_price - entry_price) / entry_price

                    setattr(sig, attr_gain, max_gain)
                    setattr(sig, attr_dd, max_dd)

            signals.append(sig)

        return signals

    # ────────────────────────────────────────────────────────
    # GÖSTERGE CACHE
    # ────────────────────────────────────────────────────────

    def _get_indicators(self, ticker: str,
                         raw_df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Göstergeleri hesapla veya cache'den al.
        Aynı hisse birden fazla strateji için test edildiğinde
        göstergeleri tekrar hesaplamaz.
        """
        if ticker in self._indicator_cache:
            return self._indicator_cache[ticker]

        try:
            df = self.indicator_engine.calculate_all(raw_df)
            self._indicator_cache[ticker] = df
            return df
        except Exception as e:
            logger.debug(f"{ticker}: Gösterge hesaplama hatası — {e}")
            return None

    def clear_cache(self):
        """Gösterge cache'ini temizle (bellek yönetimi)"""
        self._indicator_cache.clear()

    def precompute_indicators(self, all_data: Dict[str, pd.DataFrame]):
        """
        Tüm hisselerin göstergelerini önceden hesapla.
        Böylece strateji döngüsünde tekrar hesaplanmaz.
        """
        logger.info(f"Göstergeler önceden hesaplanıyor ({len(all_data)} hisse)...")

        done = 0
        for ticker, df in all_data.items():
            self._get_indicators(ticker, df)
            done += 1
            if done % 50 == 0:
                logger.info(f"  Gösterge hesaplama: {done}/{len(all_data)}")

        logger.info(f"Gösterge hesaplama tamamlandı: {done} hisse")

    # ────────────────────────────────────────────────────────
    # TRAIN / TEST SPLIT
    # ────────────────────────────────────────────────────────

    def _split_train_test(self, result: BacktestResult):
        """
        Sinyalleri tarih bazında train/test olarak ayır.
        İlk %60 → train, son %40 → test
        """
        if not result.signals:
            return

        # Tüm sinyal tarihlerini topla
        all_dates = sorted(set(s.date for s in result.signals))

        if len(all_dates) < 10:
            # Çok az tarih varsa hepsini train say
            result.train_signals = result.signals
            result.test_signals = []
            return

        # Split noktası
        split_idx = int(len(all_dates) * BACKTEST['train_ratio'])
        split_date = all_dates[split_idx]

        result.train_signals = [
            s for s in result.signals if s.date < split_date
        ]
        result.test_signals = [
            s for s in result.signals if s.date >= split_date
        ]

    # ────────────────────────────────────────────────────────
    # SEKTÖR BAZLI KORELASYON KONTROLÜ
    # ────────────────────────────────────────────────────────

    @staticmethod
    def apply_sector_correlation(
        signals: List[SignalResult]
    ) -> List[SignalResult]:
        """
        Aynı gün + aynı sektör sinyallerini tek sinyale düşür.

        Mantık:
        - Aynı gün aynı sektörde 5 sinyal varsa
        - En yüksek hacimli (en likit) olanı tut, diğerlerini at
        - Farklı sektörler bağımsız kalır
        """
        if not signals:
            return signals

        # Gün + sektör bazında grupla
        groups = defaultdict(list)
        for sig in signals:
            date_str = sig.date.strftime('%Y-%m-%d') if hasattr(
                sig.date, 'strftime'
            ) else str(sig.date)
            key = f"{date_str}_{sig.sector}"
            groups[key].append(sig)

        # Her gruptan 1 sinyal seç
        filtered = []
        for key, group_signals in groups.items():
            if len(group_signals) == 1:
                filtered.append(group_signals[0])
            else:
                # En yüksek entry_price olanı seç
                # (proxy olarak — likit hisseler genelde pahalı)
                best = max(group_signals, key=lambda s: s.entry_price)
                filtered.append(best)

        return filtered

    # ────────────────────────────────────────────────────────
    # TOPLU BACKTEST
    # ────────────────────────────────────────────────────────

    def run_batch(self, strategies: List[dict],
                   all_data: Dict[str, pd.DataFrame],
                   progress_every: int = 100) -> List[BacktestResult]:
        """
        Birden fazla stratejiyi toplu test et.

        Args:
            strategies: Strateji listesi
            all_data: Tüm hisse verileri
            progress_every: Her N stratejide progress log

        Returns:
            BacktestResult listesi
        """
        logger.info(f"{'='*50}")
        logger.info(f"Toplu backtest: {len(strategies)} strateji × "
                    f"{len(all_data)} hisse")
        logger.info(f"{'='*50}")

        # Göstergeleri önceden hesapla (en büyük optimizasyon)
        self.precompute_indicators(all_data)

        results = []

        for i, strategy in enumerate(strategies):
            bt_result = self.run(strategy, all_data)

            # Sektör korelasyon filtresi uygula
            bt_result.signals = self.apply_sector_correlation(
                bt_result.signals
            )
            bt_result.train_signals = self.apply_sector_correlation(
                bt_result.train_signals
            )
            bt_result.test_signals = self.apply_sector_correlation(
                bt_result.test_signals
            )

            results.append(bt_result)

            if (i + 1) % progress_every == 0:
                # Son stratejinin sinyal sayısını göster
                logger.info(
                    f"  Backtest: {i+1}/{len(strategies)} "
                    f"(son strateji: {bt_result.total_signals} sinyal)"
                )

        logger.info(f"Toplu backtest tamamlandı: {len(results)} sonuç")

        return results


# ════════════════════════════════════════════════════════════
# METRİK HESAPLAMA (Hızlı ön-filtre için)
# ════════════════════════════════════════════════════════════

def quick_metrics(result: BacktestResult,
                   period: int = 10) -> Optional[dict]:
    """
    Hızlı metrik hesapla. Ön-filtre için kullanılır.
    Detaylı analiz evaluator.py'de yapılır.

    Args:
        result: BacktestResult
        period: Hangi holding period (5, 10, 20)

    Returns:
        dict veya None (yetersiz sinyal)
    """
    attr = f'ret_{period}d'

    # Tüm sinyallerden getirileri al
    returns = [
        getattr(s, attr) for s in result.signals
        if getattr(s, attr) is not None
    ]

    if len(returns) < BACKTEST['min_signals_total']:
        return None

    returns = np.array(returns)

    wins = returns > 0
    win_rate = wins.mean()
    avg_return = returns.mean()

    # Train sinyalleri
    train_returns = [
        getattr(s, attr) for s in result.train_signals
        if getattr(s, attr) is not None
    ]

    # Test sinyalleri
    test_returns = [
        getattr(s, attr) for s in result.test_signals
        if getattr(s, attr) is not None
    ]

    # Benzersiz hisse ve ay sayısı
    unique_tickers = len(set(s.ticker for s in result.signals))
    unique_months = len(set(
        s.date.strftime('%Y-%m') if hasattr(s.date, 'strftime')
        else str(s.date)[:7]
        for s in result.signals
    ))

    metrics = {
        'total_signals': len(returns),
        'train_signals': len(train_returns),
        'test_signals': len(test_returns),
        'win_rate': float(win_rate),
        'avg_return': float(avg_return),
        'median_return': float(np.median(returns)),
        'std_return': float(np.std(returns)),
        'unique_tickers': unique_tickers,
        'unique_months': unique_months,
        'period': period,
    }

    # Test metrikleri (varsa)
    if len(test_returns) >= 10:
        test_arr = np.array(test_returns)
        metrics['test_win_rate'] = float((test_arr > 0).mean())
        metrics['test_avg_return'] = float(test_arr.mean())
    else:
        metrics['test_win_rate'] = None
        metrics['test_avg_return'] = None

    return metrics


def passes_quick_filter(metrics: dict) -> bool:
    """
    Hızlı ön-filtre. Değmeyecek stratejileri hemen ele.
    Detaylı analiz sadece bu filtreyi geçenler için yapılır.
    """
    if metrics is None:
        return False

    # Minimum sinyal
    if metrics['total_signals'] < BACKTEST['min_signals_total']:
        return False

    # Minimum kazanma oranı 
