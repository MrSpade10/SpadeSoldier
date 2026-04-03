# ============================================================
# app.py — Render Free Web Service + İç Zamanlayıcı
# ============================================================

import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify

app = Flask(__name__)

status = {
    "last_scan": None,
    "last_signals": None,
    "running": False,
    "result": None,
    "started_at": datetime.now().isoformat(),
    "scheduler": "waiting",
}

# ════════════════════════════════════════════════════════════
# FLASK ENDPOINT'LER
# ════════════════════════════════════════════════════════════

@app.route("/")
def home():
    return jsonify({
        "service": "BIST Strategy Discovery",
        "status": "running",
        "last_scan": status["last_scan"],
        "last_signals": status["last_signals"],
        "is_scanning": status["running"],
        "scheduler": status["scheduler"],
        "uptime_since": status["started_at"],
    })

@app.route("/health")
def health():
    return "OK", 200

@app.route("/run-test")
def run_test():
    if status["running"]:
        return jsonify({"error": "Zaten çalışıyor"}), 429

    def _test():
        status["running"] = True
        try:
            from main import run_quick_test
            run_quick_test()
            status["result"] = "test_ok"
        except Exception as e:
            status["result"] = f"error: {e}"
        finally:
            status["running"] = False

    threading.Thread(target=_test, daemon=True).start()
    return jsonify({"message": "Test başlatıldı, Telegram'ı kontrol et"})

@app.route("/run-scan")
def run_scan():
    if status["running"]:
        return jsonify({"error": "Zaten çalışıyor"}), 429

    def _scan():
        status["running"] = True
        try:
            from main import run_discovery
            from config import BIST_TICKERS, BACKTEST
            run_discovery(
                tickers=BIST_TICKERS,
                n_strategies=BACKTEST['n_random_strategies'],
                notify=True
            )
            status["last_scan"] = datetime.now().isoformat()
            status["result"] = "scan_ok"
        except Exception as e:
            status["result"] = f"error: {e}"
        finally:
            status["running"] = False

    threading.Thread(target=_scan, daemon=True).start()
    return jsonify({"message": "Tam tarama başlatıldı"})

@app.route("/run-signals")
def run_signals():
    if status["running"]:
        return jsonify({"error": "Zaten çalışıyor"}), 429

    def _signals():
        status["running"] = True
        try:
            from main import check_today_signals
            check_today_signals()
            status["last_signals"] = datetime.now().isoformat()
            status["result"] = "signals_ok"
        except Exception as e:
            status["result"] = f"error: {e}"
        finally:
            status["running"] = False

    threading.Thread(target=_signals, daemon=True).start()
    return jsonify({"message": "Sinyal kontrolü başlatıldı"})

# ════════════════════════════════════════════════════════════
# İÇ ZAMANLEYICI
# ════════════════════════════════════════════════════════════

def scheduler_thread():
    """
    Arka planda çalışan zamanlayıcı.
    23:00 → Tam tarama
    09:30 → Bugünkü sinyaller
    """
    # Türkiye saati = UTC+3
    # Render UTC kullanır
    # 23:00 TR = 20:00 UTC
    # 09:30 TR = 06:30 UTC

    SCAN_HOUR_UTC = 20     # 23:00 Türkiye
    SCAN_MINUTE = 0
    SIGNAL_HOUR_UTC = 6    # 09:30 Türkiye
    SIGNAL_MINUTE = 30

    last_scan_date = None
    last_signal_date = None

    status["scheduler"] = "active"

    while True:
        try:
            now = datetime.utcnow()
            today = now.date()

            # ── Gece tarama: 23:00 TR (20:00 UTC) ──
            if (now.hour == SCAN_HOUR_UTC and
                    now.minute < 5 and
                    last_scan_date != today and
                    not status["running"]):

                last_scan_date = today
                status["scheduler"] = f"scanning ({now.strftime('%H:%M')} UTC)"

                try:
                    from main import run_discovery
                    from config import BIST_TICKERS, BACKTEST

                    status["running"] = True
                    run_discovery(
                        tickers=BIST_TICKERS,
                        n_strategies=BACKTEST['n_random_strategies'],
                        notify=True
                    )
                    status["last_scan"] = datetime.now().isoformat()
                except Exception as e:
                    from reporter import TelegramReporter
                    tg = TelegramReporter()
                    tg.send_error(f"Gece tarama hatası: {e}")
                finally:
                    status["running"] = False
                    status["scheduler"] = "active"

            # ── Sabah sinyaller: 09:30 TR (06:30 UTC) ──
            if (now.hour == SIGNAL_HOUR_UTC and
                    now.minute >= SIGNAL_MINUTE and
                    now.minute < SIGNAL_MINUTE + 5 and
                    last_signal_date != today and
                    not status["running"]):

                last_signal_date = today
                status["scheduler"] = f"checking signals ({now.strftime('%H:%M')} UTC)"

                try:
                    from main import check_today_signals

                    status["running"] = True
                    check_today_signals()
                    status["last_signals"] = datetime.now().isoformat()
                except Exception as e:
                    from reporter import TelegramReporter
                    tg = TelegramReporter()
                    tg.send_error(f"Sinyal kontrol hatası: {e}")
                finally:
                    status["running"] = False
                    status["scheduler"] = "active"

        except Exception as e:
            status["scheduler"] = f"error: {e}"

        time.sleep(30)


# Zamanlayıcıyı başlat (uygulama açılınca 1 kez)
scheduler = threading.Thread(target=scheduler_thread, daemon=True)
scheduler.start()

# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
