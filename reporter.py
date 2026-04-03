# ============================================================
# reporter.py — Telegram Bildirim + JSON Kayıt
# ============================================================
# PARÇA 5/5 | Versiyon: 1.0
# Sonuçları Telegram'a gönderir, JSON dosyasına kaydeder,
# PostgreSQL'e kaydeder.
# ============================================================

import json
import time
from datetime import datetime
from typing import List, Optional
from pathlib import Path

import telebot

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    RESULTS_DIR, DATABASE_URL, logger
)

import psycopg2


class TelegramReporter:
    """Telegram üzerinden sonuç bildirimi"""

    def __init__(self):
        if not TELEGRAM_BOT_TOKEN:
            logger.warning("TELEGRAM_BOT_TOKEN ayarlanmamış!")
            self.bot = None
            return

        try:
            self.bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
            self.chat_id = TELEGRAM_CHAT_ID
            logger.info("Telegram bot başlatıldı")
        except Exception as e:
            logger.error(f"Telegram bot hatası: {e}")
            self.bot = None

    def send_message(self, text: str) -> bool:
        """Tek mesaj gönder"""
        if not self.bot or not self.chat_id:
            logger.warning("Telegram gönderilemedi (bot/chat_id yok)")
            return False

        try:
            # Telegram 4096 karakter limiti
            if len(text) <= 4096:
                self.bot.send_message(
                    self.chat_id, text,
                    parse_mode=None  # düz metin
                )
            else:
                # Uzun mesajı parçala
                chunks = self._split_message(text, 4096)
                for chunk in chunks:
                    self.bot.send_message(
                        self.chat_id, chunk,
                        parse_mode=None
                    )
                    time.sleep(0.5)  # Rate limit

            logger.info(f"Telegram mesajı gönderildi ({len(text)} karakter)")
            return True

        except Exception as e:
            logger.error(f"Telegram gönderim hatası: {e}")
            return False

    def send_strategy_alert(self, message: str) -> bool:
        """Strateji keşif bildirimi gönder"""
        return self.send_message(message)

    def send_summary(self, summary: str) -> bool:
        """Toplu sonuç özeti gönder"""
        return self.send_message(summary)

    def send_start_notification(self, n_tickers: int,
                                  n_strategies: int):
        """Tarama başladı bildirimi"""
        msg = (
            f"🔄 Strateji Tarama Başladı\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Hisse sayısı: {n_tickers}\n"
            f"🔬 Test edilecek strateji: {n_strategies}\n"
            f"⏰ Başlangıç: {datetime.now().strftime('%H:%M:%S')}\n"
            f"\nSonuçlar hazır olunca bildireceğim..."
        )
        self.send_message(msg)

    def send_completion(self, n_tested: int, n_passed: int,
                         duration_minutes: float):
        """Tarama bitti bildirimi"""
        msg = (
            f"✅ Strateji Tarama Tamamlandı\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔬 Test edilen: {n_tested}\n"
            f"🏆 Başarılı: {n_passed}\n"
            f"⏱️ Süre: {duration_minutes:.1f} dakika\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        self.send_message(msg)

    def send_error(self, error_msg: str):
        """Hata bildirimi"""
        msg = (
            f"❌ Strateji Tarama Hatası\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{error_msg}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send_message(msg)

    @staticmethod
    def _split_message(text: str, max_len: int) -> list:
        """Uzun mesajı satır bazında parçala"""
        lines = text.split('\n')
        chunks = []
        current = []
        current_len = 0

        for line in lines:
            if current_len + len(line) + 1 > max_len:
                chunks.append('\n'.join(current))
                current = [line]
                current_len = len(line)
            else:
                current.append(line)
                current_len += len(line) + 1

        if current:
            chunks.append('\n'.join(current))

        return chunks

    def test_connection(self) -> bool:
        """Telegram bağlantısını test et"""
        if not self.bot:
            return False
        try:
            self.bot.get_me()
            logger.info("Telegram bağlantısı OK")
            return True
        except Exception as e:
            logger.error(f"Telegram bağlantı testi başarısız: {e}")
            return False


class JSONReporter:
    """Sonuçları JSON dosyasına kaydet"""

    def __init__(self):
        RESULTS_DIR.mkdir(exist_ok=True)

    def save(self, metrics_list: list,
             filename: str = None) -> Path:
        """
        Sonuçları JSON dosyasına kaydet.

        Args:
            metrics_list: StrategyMetrics.to_dict() listesi
            filename: Dosya adı (varsayılan: tarih bazlı)

        Returns:
            Kaydedilen dosya yolu
        """
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"results_{timestamp}.json"

        filepath = RESULTS_DIR / filename

        # Tuple'ları list'e çevir (JSON uyumluluk)
        clean_data = self._clean_for_json(metrics_list)

        output = {
            'generated_at': datetime.now().isoformat(),
            'total_strategies': len(clean_data),
            'strategies': clean_data,
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"Sonuçlar kaydedildi: {filepath}")
        return filepath

    def _clean_for_json(self, data):
        """Tuple, numpy vb. tipleri JSON uyumlu yap"""
        if isinstance(data, dict):
            return {
                str(k): self._clean_for_json(v)
                for k, v in data.items()
            }
        elif isinstance(data, (list, tuple)):
            return [self._clean_for_json(item) for item in data]
        elif isinstance(data, (int, float, str, bool, type(None))):
            return data
        else:
            return str(data)


class DBReporter:
    """Sonuçları PostgreSQL'e kaydet"""

    def __init__(self):
        try:
            self.conn = psycopg2.connect(DATABASE_URL)
            self.conn.autocommit = True
        except Exception as e:
            logger.error(f"DBReporter bağlantı hatası: {e}")
            self.conn = None

    def save_strategy(self, metrics) -> bool:
        """Başarılı stratejiyi DB'ye kaydet"""
        if not self.conn:
            return False

        try:
            with self.conn.cursor() as cur:
                # Params'daki tuple'ları list'e çevir
                params_clean = {}
                for k, v in metrics.strategy_params.items():
                    if isinstance(v, tuple):
                        params_clean[k] = list(v)
                    else:
                        params_clean[k] = v

                train_metrics = {
                    'win_rate_10d': metrics.win_rate_10d,
                    'avg_return_10d': metrics.avg_return_10d,
                    'sharpe_10d': metrics.sharpe_10d,
                    'profit_factor_10d': metrics.profit_factor_10d,
                    'total_signals': metrics.total_signals,
                    'avg_max_dd_10d': metrics.avg_max_dd_10d,
                    'avg_max_gain_10d': metrics.avg_max_gain_10d,
                }

                test_metrics = {
                    'oos_win_rate_10d': metrics.oos_win_rate_10d,
                    'oos_avg_return_10d': metrics.oos_avg_return_10d,
                    'oos_sharpe_10d': metrics.oos_sharpe_10d,
                    'test_signals': metrics.test_signals,
                }

                cur.execute("""
                    INSERT INTO discovered_strategies
                        (strategy_hash, parameters, train_metrics,
                         test_metrics, p_value, top_tickers, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'new')
                    ON CONFLICT (strategy_hash) DO UPDATE SET
                        train_metrics = EXCLUDED.train_metrics,
                        test_metrics = EXCLUDED.test_metrics,
                        p_value = EXCLUDED.p_value,
                        top_tickers = EXCLUDED.top_tickers,
                        discovered_at = NOW()
                """, (
                    metrics.strategy_hash,
                    json.dumps(params_clean),
                    json.dumps(train_metrics),
                    json.dumps(test_metrics),
                    metrics.p_value,
                    json.dumps(metrics.top_tickers, default=str),
                ))

                logger.info(
                    f"Strateji DB'ye kaydedildi: {metrics.strategy_hash}"
                )
                return True

        except Exception as e:
            logger.error(f"DB kayıt hatası: {e}")
            return False

    def close(self):
        if self.conn and not self.conn.closed:
            self.conn.close()


# ════════════════════════════════════════════════════════════
# REPORTER FABRİKASI
# ════════════════════════════════════════════════════════════

class ReporterManager:
    """Tüm reporter'ları yönetir"""

    def __init__(self):
        self.telegram = TelegramReporter()
        self.json_reporter = JSONReporter()
        self.db = DBReporter()

    def report_results(self, passed_metrics: list,
                        total_tested: int):
        """
        Tüm sonuçları raporla:
        1. Her başarılı strateji → Telegram mesajı
        2. Özet → Telegram mesajı
        3. Tümü → JSON dosyası
        4. Tümü → PostgreSQL
        """
        from evaluator import ResultFormatter

        formatter = ResultFormatter()

        # ── 1. JSON kayıt (her zaman) ──
        json_data = formatter.to_json(passed_metrics)
        filepath = self.json_reporter.save(json_data)

        # ── 2. DB kayıt ──
        for m in passed_metrics:
            self.db.save_strategy(m)

        # ── 3. Telegram bildirimleri ──
        if not passed_metrics:
            self.telegram.send_message(
                f"📊 Tarama tamamlandı\n"
                f"Test edilen: {total_tested}\n"
                f"Başarılı strateji: 0\n"
                f"Kriterleri karşılayan strateji bulunamadı."
            )
            return

        # Özet mesaj
        summary = formatter.to_summary_message(
            passed_metrics, total_tested
        )
        self.telegram.send_summary(summary)
        time.sleep(1)

        # En iyi 5 strateji detaylı mesaj
        for m in passed_metrics[:5]:
            detail = formatter.to_telegram_message(m)
            self.telegram.send_strategy_alert(detail)
            time.sleep(1)  # Telegram rate limit

        if len(passed_metrics) > 5:
            self.telegram.send_message(
                f"📌 Toplam {len(passed_metrics)} başarılı strateji var.\n"
                f"İlk 5'i yukarıda gönderildi.\n"
                f"Tümü JSON dosyasında: {filepath.name}"
            )

    def close(self):
        self.db.close()


# ════════════════════════════════════════════════════════════
# TEST
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 50)
    print("Reporter Test")
    print("=" * 50)

    # Telegram test
    tg = TelegramReporter()
    if tg.test_connection():
        print("✅ Telegram bağlantısı OK")
        tg.send_message("🧪 Strateji Keşif Sistemi — Test mesajı")
        print("✅ Test mesajı gönderildi, Telegram'ı kontrol et")
    else:
        print("❌ Telegram bağlantısı başarısız")

    # JSON test
    jr = JSONReporter()
    test_data = [{"test": True, "score": 42}]
    path = jr.save(test_data, "test_output.json")
    print(f"✅ JSON test dosyası: {path}")

    # DB test
    db = DBReporter()
    if db.conn:
        print("✅ DB bağlantısı OK")
    db.close()

    print("\n✅ Reporter test tamamlandı!")
