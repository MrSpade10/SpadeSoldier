# ============================================================
# strategy_generator.py — Rastgele Strateji Üretici
# ============================================================
# PARÇA 3/5 | Versiyon: 1.0
# Random Search ile parametre kombinasyonları üretir.
# Seed ile tekrarlanabilir.
# ============================================================

import random
import hashlib
import json
from typing import List, Dict

from config import PARAMETER_SPACE, BACKTEST, logger


class StrategyGenerator:
    """
    PARAMETER_SPACE'den rastgele strateji kombinasyonları üretir.
    Her strateji bir dict: {"rsi_range": (40,60), "macd_condition": "histogram_positive", ...}
    """

    def __init__(self, seed: int = None):
        self.seed = seed or BACKTEST['random_seed']
        self.rng = random.Random(self.seed)
        logger.info(f"StrategyGenerator başlatıldı (seed={self.seed})")

    def generate(self, n: int = None) -> List[Dict]:
        """
        N adet rastgele strateji üret.

        Args:
            n: Kaç strateji üretilecek (varsayılan: config'den)

        Returns:
            List of strategy dicts
        """
        n = n or BACKTEST['n_random_strategies']

        strategies = []
        seen_hashes = set()

        attempts = 0
        max_attempts = n * 3  # Tekrar önleme

        while len(strategies) < n and attempts < max_attempts:
            attempts += 1

            strategy = self._random_strategy()

            # Minimum filtre kontrolü — en az 3 aktif filtre olsun
            active_filters = sum(
                1 for v in strategy.values() if v is not None
            )
            if active_filters < 3:
                continue

            # Tekrar kontrolü
            s_hash = self._hash_strategy(strategy)
            if s_hash in seen_hashes:
                continue

            seen_hashes.add(s_hash)
            strategy['_hash'] = s_hash
            strategy['_id'] = len(strategies) + 1
            strategies.append(strategy)

        logger.info(
            f"{len(strategies)} strateji üretildi "
            f"({attempts} deneme, {len(seen_hashes)} benzersiz)"
        )

        return strategies

    def _random_strategy(self) -> Dict:
        """Tek bir rastgele strateji üret"""
        strategy = {}

        for param_name, param_values in PARAMETER_SPACE.items():
            strategy[param_name] = self.rng.choice(param_values)

        return strategy

    @staticmethod
    def _hash_strategy(strategy: dict) -> str:
        """Strateji için benzersiz hash üret (tekrar önleme)"""
        # _hash ve _id alanlarını çıkar
        clean = {
            k: v for k, v in strategy.items()
            if not k.startswith('_')
        }

        # Tuple'ları string'e çevir (JSON serializable)
        serializable = {}
        for k, v in clean.items():
            if isinstance(v, tuple):
                serializable[k] = list(v)
            else:
                serializable[k] = v

        raw = json.dumps(serializable, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    @staticmethod
    def strategy_to_text(strategy: dict) -> str:
        """Strateji parametrelerini okunabilir metin yap"""
        lines = []

        label_map = {
            'rsi_range': 'RSI',
            'macd_condition': 'MACD',
            'volume_multiplier': 'Hacim',
            'price_vs_sma50': 'Fiyat/SMA50',
            'adx_threshold': 'ADX',
            'price_vs_sma200': 'Fiyat/SMA200',
            'ema_cross': 'EMA Cross',
            'bollinger_position': 'Bollinger',
            'obv_trend': 'OBV',
            'vwap_position': 'VWAP',
            'recent_performance': 'Son 20g Perf',
        }

        value_map = {
            'histogram_positive': 'Histogram > 0',
            'histogram_negative': 'Histogram < 0',
            'histogram_turning_up': 'Histogram artıyor',
            'crossover_up': 'Yukarı kesişim',
            'crossover_down': 'Aşağı kesişim',
            'above': 'Üstünde',
            'below': 'Altında',
            'near': 'Yakın (±%2)',
            'bullish': 'Boğa (EMA9>EMA21)',
            'bearish': 'Ayı (EMA9<EMA21)',
            'golden_cross': 'Altın kesişim',
            'death_cross': 'Ölüm kesişimi',
            'near_lower': 'Alt banda yakın',
            'near_upper': 'Üst banda yakın',
            'squeeze': 'Sıkışma',
            'breakout_up': 'Üst band kırılımı',
            'rising': 'Yükseliyor',
            'falling': 'Düşüyor',
            'divergence': 'Boğa diverjansı',
        }

        for param, label in label_map.items():
            if param not in strategy or strategy[param] is None:
                continue

            value = strategy[param]

            if isinstance(value, tuple):
                if param == 'rsi_range':
                    text = f"{value[0]}-{value[1]}"
                elif param == 'recent_performance':
                    text = f"%{value[0]*100:.0f} ile %{value[1]*100:.0f}"
                else:
                    text = str(value)
            elif isinstance(value, (int, float)):
                if param == 'volume_multiplier':
                    text = f"> {value}x ortalama"
                elif param == 'adx_threshold':
                    text = f"> {value}"
                else:
                    text = str(value)
            elif isinstance(value, str):
                text = value_map.get(value, value)
            else:
                text = str(value)

            lines.append(f"  {label}: {text}")

        return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# TEST
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 50)
    print("Strategy Generator Test")
    print("=" * 50)

    gen = StrategyGenerator(seed=42)
    strategies = gen.generate(n=5)

    for s in strategies:
        print(f"\n── Strateji #{s['_id']} ({s['_hash']}) ──")
        print(gen.strategy_to_text(s))

    # Tekrarlanabilirlik testi
    gen2 = StrategyGenerator(seed=42)
    strategies2 = gen2.generate(n=5)
    assert strategies[0]['_hash'] == strategies2[0]['_hash']
    print("\n✅ Tekrarlanabilirlik testi geçti!")
