# ============================================================
# main.py — Strateji Keşif Sistemi Ana Giriş Noktası
# ============================================================
# PARÇA 5/5 | Versiyon: 1.0
#
# Kullanım:
#   Manuel:    python main.py --tickers THYAO,EREGL,AKBNK
#   Tüm BIST: python main.py --all
#   Test:      python main.py --test
#   Zamanlı:   python main.py --schedule
#
# ============================================================

import argparse
import time
import sys
import signal
import json
from datetime import datetime
from pathlib import Path

# Modüller
from config import (
    BACKTEST, BIST_TICKERS, RESULTS_DIR,
    logger, TELEGRAM_CHAT_ID
)
from data_loader import DataLoader
from indicators import IndicatorEngine
from strategy_generator import StrategyGenerator
from backtester import Backtester
from evaluator import StrategyEvaluator, ResultFormatter
from reporter import ReporterManager, TelegramReporter


# ════════════════════════════════════════════════════════════
# ANA TARAMA FONKSİYONU
# ════════════════════════════════════════════════════════════

def run_discovery(tickers: list,
                   n_strategies: int = None,
                   seed: int = None,
                   notify: bool = True) -> list:
    """
    Ana strateji keşif fonksiyonu.

    Args:
        tickers: Taranacak hisse listesi
        n_strategies: Kaç strateji test edilecek
        seed: Random seed
        notify: Telegram bildirimi gönder

    Returns:
        Başarılı StrategyMetrics listesi
    """

    start_time = time.time()
    n_strategies = n_strategies or BACKTEST['n_random_strategies']

    logger.info("=" * 60)
    logger.info("🔬 STRATEJİ KEŞİF SİSTEMİ BAŞLATILIYOR")
    logger.info(f"   Hisse: {len(tickers)}")
    logger.info(f"   Strateji: {n_strategies}")
    logger.info(f"   Seed: {seed or BACKTEST['random_seed']}")
    logger.info(f"   Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Reporter
    reporter = ReporterManager()

    if notify:
        reporter.telegram.send_start_notification(
            len(tickers), n_strategies
        )

    try:
        # ── ADIM 1: Veri Yükleme ──
        logger.info("\n📊 ADIM 1/4: Veri yükleniyor...")
        loader = DataLoader()
        all_data = loader.load_all(
            tickers,
            interval="1d",
            period=BACKTEST['daily_range'],
            max_cache_age=1
        )
        loader.close()

        if len(all_data) < 5:
            msg = f"Yetersiz veri: {len(all_data)} hisse yüklendi"
            logger.error(msg)
            if notify:
                reporter.telegram.send_error(msg)
            return []

        logger.info(f"✅ {len(all_data)} hisse yüklendi\n")

        # ── ADIM 2: Strateji Üretme ──
        logger.info("🔬 ADIM 2/4: Stratejiler üretiliyor...")
        generator = StrategyGenerator(seed=seed)
        strategies = generator.generate(n=n_strategies)
        logger.info(f"✅ {len(strategies)} strateji üretildi\n")

        # ── ADIM 3: Backtest ──
        logger.info("📈 ADIM 3/4: Backtest çalışıyor...")
        backtester = Backtester()
        bt_results = backtester.run_batch(
            strategies, all_data,
            progress_every=max(1, len(strategies) // 10)
        )
        logger.info(f"✅ {len(bt_results)} backtest tamamlandı\n")

        # ── ADIM 4: Değerlendirme ──
        logger.info("🧪 ADIM 4/4: Değerlendirme ve istatistik...")
        evaluator = StrategyEvaluator()
        passed_metrics = evaluator.evaluate_batch(
            bt_results, quick_filter=True
        )

        # ── Süre hesapla ──
        elapsed = (time.time() - start_time) / 60

        logger.info("=" * 60)
        logger.info(f"🏁 TARAMA TAMAMLANDI")
        logger.info(f"   Süre: {elapsed:.1f} dakika")
        logger.info(f"   Test edilen: {len(strategies)}")
        logger.info(f"   Başarılı: {len(passed_metrics)}")
        logger.info("=" * 60)

        # ── Sonuçları raporla ──
        if notify:
            reporter.telegram.send_completion(
                len(strategies), len(passed_metrics), elapsed
            )

        reporter.report_results(passed_metrics, len(strategies))
        reporter.close()

        return passed_metrics

    except Exception as e:
        logger.error(f"Kritik hata: {e}", exc_info=True)
        if notify:
            reporter.telegram.send_error(str(e))
        return []


# ════════════════════════════════════════════════════════════
# ZAMANLANMIŞ ÇALIŞMA
# ════════════════════════════════════════════════════════════

def run_scheduled():
    """
    Gece 23:00'de tarama başlat, sabah sonuçları bildir.
    Basit sleep-based scheduler (APScheduler gerektirmez).
    """
    import schedule

    logger.info("⏰ Zamanlı mod başlatıldı")
    logger.info("   Tarama: Her gece 23:00")
    logger.info("   Ctrl+C ile durdurun")

    def nightly_scan():
        logger.info("🌙 Gece taraması başlıyor...")
        run_discovery(
            tickers=BIST_TICKERS,
            n_strategies=BACKTEST['n_random_strategies'],
            notify=True
        )

    # Her gece 23:00'de çalıştır
    schedule.every().day.at("23:00").do(nightly_scan)

    # Başlangıç bildirimi
    tg = TelegramReporter()
    tg.send_message(
        "⏰ Zamanlı mod aktif\n"
        "Her gece 23:00'de tüm BIST taranacak.\n"
        f"Hisse sayısı: {len(BIST_TICKERS)}\n"
        f"Strateji sayısı: {BACKTEST['n_random_strategies']}"
    )

    # Sonsuz döngü
    while True:
        schedule.run_pending()
        time.sleep(60)  # Her dakika kontrol et


def run_scheduled_simple():
    """
    schedule kütüphanesi yoksa basit alternatif.
    """
    from datetime import time as dt_time

    logger.info("⏰ Zamanlı mod başlatıldı (basit)")
    logger.info("   Tarama: Her gece 23:00")

    tg = TelegramReporter()
    tg.send_message(
        "⏰ Zamanlı mod aktif (basit scheduler)\n"
        f"Hisse: {len(BIST_TICKERS)} | "
        f"Strateji: {BACKTEST['n_random_strategies']}"
    )

    last_run_date = None

    while True:
        now = datetime.now()

        # Saat 23:00-23:05 arasında ve bugün henüz çalışmadıysa
        if (now.hour == 23 and now.minute < 5 and
                last_run_date != now.date()):

            last_run_date = now.date()
            logger.info("🌙 Gece taraması tetiklendi")

            run_discovery(
                tickers=BIST_TICKERS,
                n_strategies=BACKTEST['n_random_strategies'],
                notify=True
            )

        time.sleep(30)  # 30 saniyede bir kontrol


# ════════════════════════════════════════════════════════════
# HIZLI TEST
# ════════════════════════════════════════════════════════════

def run_quick_test():
    """
    Her şeyin çalıştığını doğrulayan hızlı test.
    3 hisse, 10 strateji, Telegram bildirim.
    """
    print("=" * 60)
    print("🧪 HIZLI TEST MODU")
    print("=" * 60)

    # 1. Telegram test
    print("\n1️⃣ Telegram bağlantısı test ediliyor...")
    tg = TelegramReporter()
    if tg.test_connection():
        print("   ✅ Telegram OK")
        tg.send_message("🧪 Strateji Keşif Sistemi — Hızlı test başladı")
    else:
        print("   ❌ Telegram bağlantısı başarısız!")
        print("   Token ve Chat ID kontrol et.")
        return

    # 2. DB test
    print("\n2️⃣ PostgreSQL bağlantısı test ediliyor...")
    try:
        loader = DataLoader()
        stats = loader.cache_stats()
        print(f"   ✅ DB OK — {stats}")
    except Exception as e:
        print(f"   ❌ DB hatası: {e}")
        return

    # 3. Veri çekme test
    print("\n3️⃣ Yahoo Finance test ediliyor...")
    test_tickers = ["THYAO", "EREGL", "AKBNK"]
    all_data = loader.load_all(test_tickers, max_cache_age=7)
    loader.close()

    if len(all_data) < 2:
        print("   ❌ Veri çekme başarısız!")
        return
    print(f"   ✅ {len(all_data)} hisse yüklendi")

    # 4. Gösterge test
    print("\n4️⃣ Gösterge hesaplama test ediliyor...")
    engine = IndicatorEngine()
    test_ticker = list(all_data.keys())[0]
    df = engine.calculate_all(all_data[test_ticker])
    n_indicators = len([c for c in df.columns
                         if c not in ['open','high','low','close','volume']])
    print(f"   ✅ {n_indicators} gösterge hesaplandı ({test_ticker})")

    # 5. Strateji üretim + backtest test
    print("\n5️⃣ Strateji üretim ve backtest test ediliyor...")
    gen = StrategyGenerator(seed=42)
    strategies = gen.generate(n=10)
    print(f"   ✅ {len(strategies)} strateji üretildi")

    backtester = Backtester()
    bt_results = backtester.run_batch(strategies, all_data, progress_every=5)

    total_signals = sum(r.total_signals for r in bt_results)
    print(f"   ✅ Backtest tamamlandı — toplam {total_signals} sinyal")

    # 6. Değerlendirme test
    print("\n6️⃣ Değerlendirme test ediliyor...")
    evaluator = StrategyEvaluator()
    passed = evaluator.evaluate_batch(bt_results, quick_filter=False)
    print(f"   ✅ Değerlendirme tamamlandı — {len(passed)} başarılı")

    # Sonuç
    print("\n" + "=" * 60)
    print("✅ TÜM TESTLER BAŞARILI!")
    print("=" * 60)

    # Telegram sonuç bildirimi
    tg.send_message(
        f"✅ Hızlı Test Tamamlandı!\n\n"
        f"📊 Hisse: {len(all_data)}\n"
        f"🔬 Strateji: {len(strategies)}\n"
        f"📈 Toplam sinyal: {total_signals}\n"
        f"🏆 Başarılı: {len(passed)}\n\n"
        f"Sistem çalışmaya hazır. 🚀"
    )

    if passed:
        formatter = ResultFormatter()
        best_msg = formatter.to_telegram_message(passed[0])
        tg.send_message(best_msg)


# ════════════════════════════════════════════════════════════
# BUGÜNKÜ SİNYALLER
# ════════════════════════════════════════════════════════════

def check_today_signals():
    """
    Daha önce keşfedilmiş başarılı stratejileri
    bugünkü veriye uygula ve sinyal olan hisseleri bildir.
    """
    logger.info("📡 Bugünkü sinyaller kontrol ediliyor...")

    # DB'den başarılı stratejileri al
    try:
        conn = __import__('psycopg2').connect(DATABASE_URL)
        with conn.cursor(__import__('psycopg2').extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT strategy_hash, parameters
                FROM discovered_strategies
                WHERE status = 'new'
                ORDER BY discovered_at DESC
                LIMIT 10
            """)
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"DB okuma hatası: {e}")
        return

    if not rows:
        logger.info("Kayıtlı strateji yok")
        return

    logger.info(f"{len(rows)} kayıtlı strateji bulundu")

    # Veri yükle
    loader = DataLoader()
    all_data = loader.load_all(BIST_TICKERS, max_cache_age=0)
    loader.close()

    if not all_data:
        return

    # Her strateji için bugünkü sinyalleri kontrol et
    indicator_engine = IndicatorEngine()
    condition_checker = __import__('indicators').ConditionChecker()

    tg = TelegramReporter()
    today_signals = []

    for row in rows:
        params = row['parameters']
        if isinstance(params, str):
            params = json.loads(params)

        # Tuple'ları geri çevir
        for key in ['rsi_range', 'recent_performance']:
            if key in params and isinstance(params[key], list):
                params[key] = tuple(params[key])

        for ticker, raw_df in all_data.items():
            try:
                df = indicator_engine.calculate_all(raw_df)
                if df is None or len(df) == 0:
                    continue

                signals = condition_checker.check_all(df, params)

                # Son gün sinyal var mı?
                if signals.iloc[-1]:
                    today_signals.append({
                        'ticker': ticker,
                        'strategy': row['strategy_hash'],
                        'close': float(df['close'].iloc[-1]),
                        'rsi': float(df['rsi'].iloc[-1]),
                        'volume_ratio': float(df['volume_ratio'].iloc[-1]),
                    })
            except Exception:
                continue

    # Bildirimi gönder
    if today_signals:
        lines = [
            "📡 BUGÜNKÜ SİNYALLER",
            "━━━━━━━━━━━━━━━━━━━",
            f"📅 {datetime.now().strftime('%Y-%m-%d')}",
            f"🔬 {len(rows)} strateji kontrol edildi",
            f"📊 {len(today_signals)} sinyal bulundu",
            "",
        ]

        for sig in today_signals[:20]:
            lines.append(
                f"  📌 {sig['ticker']}: {sig['close']:.2f} TL "
                f"(RSI:{sig['rsi']:.0f}, "
                f"Vol:{sig['volume_ratio']:.1f}x) "
                f"[{sig['strategy'][:6]}]"
            )

        if len(today_signals) > 20:
            lines.append(f"\n  ... ve {len(today_signals)-20} sinyal daha")

        tg.send_message('\n'.join(lines))
        logger.info(f"✅ {len(today_signals)} sinyal bildirildi")
    else:
        tg.send_message(
            f"📡 Bugün sinyal yok\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d')}\n"
            f"🔬 {len(rows)} strateji kontrol edildi"
        )
        logger.info("Bugün sinyal yok")


# ════════════════════════════════════════════════════════════
# CLI GİRİŞ NOKTASI
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="BIST Otomatik Strateji Keşif Sistemi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Kullanım örnekleri:
  python main.py --test                          Hızlı test (3 hisse, 10 strateji)
  python main.py --tickers THYAO,EREGL,AKBNK     Belirli hisseler
  python main.py --tickers THYAO -n 500           500 strateji test et
  python main.py --all                            Tüm BIST (50 hisse)
  python main.py --all -n 1000                    Tüm BIST, 1000 strateji
  python main.py --schedule                       Gece 23:00 otomatik tarama
  python main.py --signals                        Bugünkü sinyalleri kontrol et
        """
    )

    # Mod seçimi
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--test', action='store_true',
        help='Hızlı test modu (3 hisse, 10 strateji)'
    )
    group.add_argument(
        '--tickers', type=str,
        help='Virgülle ayrılmış hisse kodları (THYAO,EREGL,...)'
    )
    group.add_argument(
        '--all', action='store_true',
        help='Tüm BIST hisselerini tara'
    )
    group.add_argument(
        '--schedule', action='store_true',
        help='Gece 23:00 otomatik tarama modu'
    )
    group.add_argument(
        '--signals', action='store_true',
        help='Bugünkü sinyalleri kontrol et'
    )

    # Opsiyonel parametreler
    parser.add_argument(
        '-n', '--num-strategies', type=int, default=None,
        help=f'Test edilecek strateji sayısı (varsayılan: {BACKTEST["n_random_strategies"]})'
    )
    parser.add_argument(
        '--seed', type=int, default=None,
        help=f'Random seed (varsayılan: {BACKTEST["random_seed"]})'
    )
    parser.add_argument(
        '--no-notify', action='store_true',
        help='Telegram bildirimlerini kapat'
    )

    args = parser.parse_args()

    # ── Çalıştır ──

    if args.test:
        run_quick_test()

    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]
        logger.info(f"Manuel mod: {tickers}")
        run_discovery(
            tickers=tickers,
            n_strategies=args.num_strategies,
            seed=args.seed,
            notify=not args.no_notify
        )

    elif args.all:
        logger.info(f"Tüm BIST modu: {len(BIST_TICKERS)} hisse")
        run_discovery(
            tickers=BIST_TICKERS,
            n_strategies=args.num_strategies,
            seed=args.seed,
            notify=not args.no_notify
        )

    elif args.schedule:
        try:
            run_scheduled()
        except ImportError:
            logger.info("schedule kütüphanesi yok, basit scheduler kullanılıyor")
            run_scheduled_simple()

    elif args.signals:
        check_today_signals()


# ════════════════════════════════════════════════════════════
# GRACEFUL SHUTDOWN
# ════════════════════════════════════════════════════════════

def signal_handler(sig, frame):
    logger.info("\n⛔ Kapatılıyor...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


if __name__ == "__main__":
    main()
