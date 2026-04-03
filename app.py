# ============================================================
# app.py — Render Free Web Service Wrapper
# ============================================================
# Render'ın free web service'i ayakta tutmak için
# basit Flask app + arka planda strateji tarama
# ============================================================

import os
import threading
from datetime import datetime
from flask import Flask, jsonify

app = Flask(__name__)

# Durum takibi
status = {
    "last_scan": None,
    "running": False,
    "result": None,
}

@app.route("/")
def home():
    return jsonify({
        "service": "BIST Strategy Discovery",
        "status": "running",
        "last_scan": status["last_scan"],
        "is_scanning": status["running"],
    })

@app.route("/health")
def health():
    return "OK", 200

@app.route("/run-test")
def run_test():
    """Hızlı test tetikle"""
    if status["running"]:
        return jsonify({"error": "Tarama zaten çalışıyor"}), 429

    def _test():
        status["running"] = True
        try:
            from main import run_quick_test
            run_quick_test()
            status["last_scan"] = datetime.now().isoformat()
            status["result"] = "test_ok"
        except Exception as e:
            status["result"] = f"error: {e}"
        finally:
            status["running"] = False

    threading.Thread(target=_test, daemon=True).start()
    return jsonify({"message": "Test başlatıldı"})

@app.route("/run-scan")
def run_scan():
    """Tam tarama tetikle"""
    if status["running"]:
        return jsonify({"error": "Tarama zaten çalışıyor"}), 429

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
    return jsonify({"message": "Tarama başlatıldı"})

@app.route("/run-signals")
def run_signals():
    """Bugünkü sinyalleri kontrol et"""
    if status["running"]:
        return jsonify({"error": "Tarama zaten çalışıyor"}), 429

    def _signals():
        status["running"] = True
        try:
            from main import check_today_signals
            check_today_signals()
            status["result"] = "signals_ok"
        except Exception as e:
            status["result"] = f"error: {e}"
        finally:
            status["running"] = False

    threading.Thread(target=_signals, daemon=True).start()
    return jsonify({"message": "Sinyal kontrolü başlatıldı"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
