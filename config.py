# ============================================================
# config.py — Strateji Keşif Sistemi Ayarları
# ============================================================
# Tüm ayarlar tek dosyada. Render env'den okur.
# ============================================================

import os
import pathlib
import logging
from datetime import datetime

# ────────────────────────────────────────────────────────────
# RENDER ENV'DEN OKU
# ────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://bist_user:85p0TQEK37a4J7lHy468B2lHbbC5NL1j"
    "@dpg-d77muf9r0fns7386b4b0-a.frankfurt-postgres.render.com"
    "/bist_strategy"
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Chat ID dosyadan okunacak (ilk /start'ta kaydedilir)
CHAT_ID_FILE = pathlib.Path(__file__).parent / "chat_id.txt"

def get_chat_id():
    """Kayıtlı chat ID'yi oku"""
    if CHAT_ID_FILE.exists():
        return CHAT_ID_FILE.read_text().strip()
    return None

def save_chat_id(chat_id):
    """Chat ID'yi kaydet"""
    CHAT_ID_FILE.write_text(str(chat_id))

# ────────────────────────────────────────────────────────────
# BACKTEST AYARLARI
# ────────────────────────────────────────────────────────────
BACKTEST = {
    "daily_range": "2y",
    "weekly_range": "5y",
    
    # Train/Test split
    "train_ratio": 0.60,
    "test_ratio": 0.40,
    
    # Holding period (sinyal sonrası kaç gün)
    "holding_periods": [5, 10, 20],
    
    # Random search
    "n_random_strategies": 2000,
    "random_seed": 42,
    
    # Minimum gereksinimler
    "min_data_points": 200,
    "min_signals_total": 50,
    "min_signals_oos": 20,
    "min_unique_tickers": 10,
    "min_unique_months": 6,
}

# ────────────────────────────────────────────────────────────
# BAŞARI KRİTERLERİ
# ────────────────────────────────────────────────────────────
SUCCESS_CRITERIA = {
    "min_win_rate": 0.60,
    "min_avg_return": 0.05,
    "max_avg_drawdown": -0.08,
    "min_sharpe": 1.2,
    "min_profit_factor": 1.5,
    "min_oos_win_rate": 0.55,
    "max_p_value": 0.05,
    "permutation_runs": 1000,
}

# ────────────────────────────────────────────────────────────
# PARAMETRE UZAYI — TÜM TIER'LAR
# ────────────────────────────────────────────────────────────
PARAMETER_SPACE = {
    
    # ── TIER 1 ──
    "rsi_range": [
        (20, 40), (25, 45), (30, 50), (35, 55),
        (40, 60), (45, 65), (50, 70), (55, 75), (60, 80),
    ],
    "macd_condition": [
        "histogram_positive",
        "histogram_negative",
        "histogram_turning_up",
        "crossover_up",
        "crossover_down",
    ],
    "volume_multiplier": [1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0],
    "price_vs_sma50": ["above", "below", "near"],
    
    # ── TIER 2 ──
    "adx_threshold": [15, 20, 25, 30, 35, None],
    "price_vs_sma200": ["above", "below", None],
    "ema_cross": [
        "bullish", "bearish", "golden_cross", "death_cross", None,
    ],
    "bollinger_position": [
        "near_lower", "near_upper", "squeeze", "breakout_up", None,
    ],
    
    # ── TIER 3 ──
    "obv_trend": ["rising", "falling", "divergence", None],
    "vwap_position": ["above", "below", None],
    "recent_performance": [
        (-0.15, -0.05), (-0.05, 0.00), (0.00, 0.05),
        (0.05, 0.15), (0.10, 0.25), None,
    ],
}

# ────────────────────────────────────────────────────────────
# SEKTÖR HARİTASI
# ────────────────────────────────────────────────────────────
SECTOR_MAP = {
    # Bankacılık
    "AKBNK": "BANKA", "GARAN": "BANKA", "ISCTR": "BANKA",
    "YKBNK": "BANKA", "HALKB": "BANKA", "VAKBN": "BANKA",
    "TSKB": "BANKA", "ALBRK": "BANKA", "QNBFB": "BANKA",
    "SKBNK": "BANKA",
    
    # Havacılık
    "THYAO": "HAVACILIK", "PGSUS": "HAVACILIK", "CLEBI": "HAVACILIK",
    
    # Demir Çelik
    "EREGL": "DEMIR_CELIK", "KRDMD": "DEMIR_CELIK",
    
    # Enerji
    "TUPRS": "ENERJI", "AKSEN": "ENERJI", "ODAS": "ENERJI",
    "ZOREN": "ENERJI", "AYDEM": "ENERJI", "AYGAZ": "ENERJI",
    
    # Otomotiv
    "TOASO": "OTOMOTIV", "FROTO": "OTOMOTIV", "DOAS": "OTOMOTIV",
    
    # Perakende
    "BIMAS": "PERAKENDE", "MGROS": "PERAKENDE", "SOKM": "PERAKENDE",
    
    # Telekom
    "TCELL": "TELEKOM", "TTKOM": "TELEKOM",
    
    # Holding
    "SAHOL": "HOLDING", "KCHOL": "HOLDING", "KOZAL": "HOLDING",
    "TAVHL": "HOLDING", "DOHOL": "HOLDING",
    
    # Teknoloji
    "LOGO": "TEKNOLOJI", "INDES": "TEKNOLOJI", "ARENA": "TEKNOLOJI",
    
    # Cam
    "SISE": "CAM", "TRKCM": "CAM", "ANACM": "CAM",
    
    # Sigorta
    "AKGRT": "SIGORTA", "ANHYT": "SIGORTA", "AGESA": "SIGORTA",
    
    # Kimya
    "PETKM": "KIMYA", "AKSA": "KIMYA", "SODA": "KIMYA", "GUBRF": "KIMYA",
    
    # Gıda
    "ULKER": "GIDA", "TATGD": "GIDA", "CCOLA": "GIDA", "KNFRT": "GIDA",
    
    # GYO
    "EKGYO": "GYO", "HLGYO": "GYO", "ISGYO": "GYO",
    
    # Savunma
    "ASELS": "SAVUNMA",
}

DEFAULT_SECTOR = "DIGER"

def get_sector(ticker):
    return SECTOR_MAP.get(ticker, DEFAULT_SECTOR)

# ────────────────────────────────────────────────────────────
# TÜM BIST HİSSELERİ
# ────────────────────────────────────────────────────────────
# Ana liste — 527 hisseyi buraya ekleyeceğiz
# Şimdilik en likit 50 hisse ile başlıyoruz
BIST_TICKERS = [
    "THYAO", "EREGL", "AKBNK", "GARAN", "TUPRS",
    "BIMAS", "SISE", "TOASO", "TCELL", "SAHOL",
    "KCHOL", "FROTO", "ASELS", "ISCTR", "YKBNK",
    "HALKB", "VAKBN", "PGSUS", "TAVHL", "DOHOL",
    "AKSEN", "ODAS", "MGROS", "SOKM", "PETKM",
    "KOZAL", "KRDMD", "LOGO", "TTKOM", "GUBRF",
    "SODA", "AKSA", "ULKER", "CCOLA", "DOAS",
    "TSKB", "ALBRK", "EKGYO", "CLEBI", "AGESA",
    "TATGD", "INDES", "ARENA", "TRKCM", "ANACM",
    "ZOREN", "AYDEM", "AYGAZ", "KNFRT", "ISGYO",
]

# ────────────────────────────────────────────────────────────
# DOSYA YOLLARI
# ────────────────────────────────────────────────────────────
BASE_DIR = pathlib.Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"
LOGS_DIR = BASE_DIR / "logs"
RESULTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ────────────────────────────────────────────────────────────
# LOGGER
# ────────────────────────────────────────────────────────────
def setup_logger(name="strategy_discovery"):
    _logger = logging.getLogger(name)
    _logger.setLevel(logging.INFO)
    
    fh = logging.FileHandler(
        LOGS_DIR / f"discovery_{datetime.now().strftime('%Y%m%d')}.log",
        encoding="utf-8"
    )
    ch = logging.StreamHandler()
    
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    
    if not _logger.handlers:
        _logger.addHandler(fh)
        _logger.addHandler(ch)
    
    return _logger

logger = setup_logger()
