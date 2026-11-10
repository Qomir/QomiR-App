# -*- coding: utf-8 -*-
"""
ScalpDip — stratégie de scalping "achat de baisse brutale" (mean-reversion) pour Binance spot.

Idée : sur des paires très liquides, une chute rapide et violente sous la bande de Bollinger
basse, avec RSI effondré et pic de volume, est souvent suivie d'un petit rebond technique.
On achète ce rebond et on revend vite (+0,5 % à +1 % NET de frais), avec :
  - stop-loss fixe obligatoire (placé sur l'exchange en réel),
  - sortie forcée si le trade ne bouge pas après `sell_timeout` minutes,
  - coupe-circuit global : arrêt total des entrées + liquidation si l'équité chute de 30 %
    depuis son plus haut (persistant entre redémarrages),
  - verrou "réel" : même si dry_run=false, aucune entrée n'est faite tant que la variable
    d'environnement CONFIRM_LIVE_TRADING n'a pas la bonne valeur (double sécurité),
  - bilan quotidien envoyé sur Telegram.

IMPORTANT sur les frais dans Freqtrade :
  - minimal_roi et current_profit sont calculés NETS des frais d'achat ET de vente.
    => "0.005" dans minimal_roi = +0,5 % net (le prix doit monter d'environ +0,7 % avec 0,1 %/ordre).
  - stoploss est exprimé en variation de PRIX (hors frais).
    => stoploss -1,5 % = perte nette ≈ -1,7 % (+ slippage éventuel).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.enums import RunMode
from freqtrade.persistence import Trade
from freqtrade.strategy import (
    BooleanParameter,
    DecimalParameter,
    IntParameter,
    IStrategy,
    informative,
)

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------------------
# Réglages de sécurité (non optimisés par hyperopt, volontairement)
# ----------------------------------------------------------------------------------------
CIRCUIT_BREAKER_DRAWDOWN = 0.30          # arrêt total si équité <= 70 % du plus haut
DAILY_SUMMARY_HOUR_UTC = 20              # 20h UTC = 21h (hiver) / 22h (été) à Paris
LIVE_CONFIRM_ENV = "CONFIRM_LIVE_TRADING"
LIVE_CONFIRM_VALUE = "OUI_JE_COMPRENDS_LES_RISQUES"


class ScalpDip(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = False                     # spot uniquement, pas de levier
    process_only_new_candles = True
    startup_candle_count = 300            # suffisant pour EMA200 sur l'informative 1h

    # --- Take-profit NET des frais, dégressif dans le temps (minutes -> profit net) ---
    # 0-10 min : on vise +1 % net ; 10-20 min : +0,75 % ; après 20 min : +0,5 %.
    minimal_roi = {
        "0": 0.010,
        "10": 0.0075,
        "20": 0.005,
    }

    # --- Stop-loss obligatoire (variation de prix, hors frais) ---
    stoploss = -0.015
    trailing_stop = False

    use_exit_signal = False               # sorties = ROI / stop / timeout / coupe-circuit
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "emergency_exit": "market",
        "force_entry": "market",
        "force_exit": "market",
        "stoploss": "market",
        # Le stop est posé directement chez Binance (stop-limit) en réel :
        # il protège même si le bot / le serveur tombe.
        "stoploss_on_exchange": True,
        "stoploss_on_exchange_interval": 60,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # ------------------------------------------------------------------------------------
    # Paramètres optimisables (walk-forward : optimisés sur la fenêtre d'entraînement,
    # puis testés sur la fenêtre suivante jamais vue).
    # ------------------------------------------------------------------------------------
    buy_bb_k = DecimalParameter(1.8, 3.0, default=2.2, decimals=1, space="buy", optimize=True)
    buy_rsi_fast = IntParameter(5, 30, default=15, space="buy", optimize=True)
    buy_rsi = IntParameter(18, 40, default=30, space="buy", optimize=True)
    buy_vol_mult = DecimalParameter(1.0, 4.0, default=1.5, decimals=1, space="buy", optimize=True)
    buy_drop = DecimalParameter(0.005, 0.030, default=0.012, decimals=3, space="buy", optimize=True)
    buy_trend_guard = BooleanParameter(default=True, space="buy", optimize=True)

    sell_timeout = IntParameter(20, 180, default=60, space="sell", optimize=True)

    # ------------------------------------------------------------------------------------
    # Protections Freqtrade (activées en dry-run/réel ; en backtest avec --enable-protections)
    # Bougies de 5 min : 12 = 1 h, 288 = 24 h.
    # ------------------------------------------------------------------------------------
    @property
    def protections(self):
        return [
            # Petite pause sur une paire après chaque trade (évite de racheter le même couteau)
            {"method": "CooldownPeriod", "stop_duration_candles": 3},
            # 3 stop-loss en 6 h, toutes paires confondues -> pause globale de 6 h
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 72,
                "trade_limit": 3,
                "stop_duration_candles": 72,
                "only_per_pair": False,
            },
            # 2 stop-loss sur la même paire en 24 h -> paire bloquée 24 h
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 288,
                "trade_limit": 2,
                "stop_duration_candles": 288,
                "only_per_pair": True,
            },
            # Drawdown > 10 % sur 24 h glissantes -> pause globale de 12 h
            # (le coupe-circuit "dur" à -30 % depuis le plus haut est géré plus bas)
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 288,
                "trade_limit": 4,
                "stop_duration_candles": 144,
                "max_allowed_drawdown": 0.10,
            },
            # Paire non rentable sur 7 jours -> écartée 2 jours
            {
                "method": "LowProfitPairs",
                "lookback_period_candles": 2016,
                "trade_limit": 4,
                "stop_duration_candles": 576,
                "required_profit": 0.0,
            },
        ]

    # ------------------------------------------------------------------------------------
    # Initialisation / état persistant
    # ------------------------------------------------------------------------------------
    def bot_start(self, **kwargs) -> None:
        self._state: dict = {
            "peak_equity": None,
            "tripped": False,
            "tripped_at": None,
            "last_summary_date": None,
        }
        self._live_blocked = False
        self._state_file: Optional[Path] = None

        runmode = self.dp.runmode if self.dp else None
        if runmode in (RunMode.LIVE, RunMode.DRY_RUN):
            suffix = "live" if runmode == RunMode.LIVE else "dryrun"
            user_dir = Path(self.config.get("user_data_dir", "user_data"))
            self._state_file = user_dir / f"scalpdip_state.{suffix}.json"
            self._load_state()

        if runmode == RunMode.LIVE and os.environ.get(LIVE_CONFIRM_ENV) != LIVE_CONFIRM_VALUE:
            self._live_blocked = True
            logger.error(
                "MODE RÉEL détecté mais %s != %s : AUCUNE ENTRÉE ne sera prise. "
                "Voir CHECKLIST_REEL.md.", LIVE_CONFIRM_ENV, LIVE_CONFIRM_VALUE,
            )

        if self._state.get("tripped"):
            logger.error("Coupe-circuit DÉJÀ déclenché le %s : aucune entrée.",
                         self._state.get("tripped_at"))

    def _load_state(self) -> None:
        if self._state_file and self._state_file.exists():
            try:
                self._state.update(json.loads(self._state_file.read_text()))
            except Exception as e:  # fichier corrompu : on repart prudemment
                logger.warning("Impossible de lire %s : %s", self._state_file, e)

    def _save_state(self) -> None:
        if not self._state_file:
            return  # backtest/hyperopt : état en mémoire uniquement
        try:
            tmp = self._state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state, indent=2, default=str))
            tmp.replace(self._state_file)
        except Exception as e:
            logger.warning("Impossible d'écrire %s : %s", self._state_file, e)

    def _notify(self, msg: str) -> None:
        logger.info(msg)
        if self.dp and self.dp.runmode in (RunMode.LIVE, RunMode.DRY_RUN):
            self.dp.send_msg(msg, always_send=True)

    # ------------------------------------------------------------------------------------
    # Équité = capital de départ + profits réalisés + profits latents (mark-to-market)
    # ------------------------------------------------------------------------------------
    def _last_close(self, pair: str) -> Optional[float]:
        try:
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if df is not None and len(df):
                return float(df["close"].iloc[-1])
        except Exception:
            pass
        return None

    def _equity(self) -> Optional[float]:
        if not self.wallets:
            return None
        start = self.wallets.get_starting_balance()
        closed = sum((t.close_profit_abs or 0.0) for t in Trade.get_trades_proxy(is_open=False))
        unrealized = 0.0
        for t in Trade.get_trades_proxy(is_open=True):
            rate = self._last_close(t.pair) or t.open_rate
            try:
                unrealized += t.calc_profit(rate)
            except Exception:
                pass
        return start + closed + unrealized

    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        equity = self._equity()
        if equity is None:
            return

        st = self._state
        if self._state_file is None and not Trade.get_trades_proxy():
            # Backtest/hyperopt : nouvelle simulation (nouvel epoch) -> on réinitialise l'état
            st.update(peak_equity=None, tripped=False, tripped_at=None)
        if st.get("peak_equity") is None or equity > st["peak_equity"]:
            st["peak_equity"] = equity
            self._save_state()

        peak = st["peak_equity"]
        drawdown = 1 - equity / peak if peak else 0.0

        if not st.get("tripped") and drawdown >= CIRCUIT_BREAKER_DRAWDOWN:
            st["tripped"] = True
            st["tripped_at"] = current_time.isoformat()
            self._save_state()
            self._notify(
                "🚨 COUPE-CIRCUIT DÉCLENCHÉ 🚨\n"
                f"Équité {equity:.2f} USDT, plus haut {peak:.2f} USDT "
                f"(drawdown {drawdown:.1%} ≥ {CIRCUIT_BREAKER_DRAWDOWN:.0%}).\n"
                "Toutes les positions sont clôturées et plus AUCUNE entrée ne sera prise.\n"
                "Pour réarmer : analyser, puis supprimer user_data/scalpdip_state.*.json "
                "et redémarrer."
            )

        self._maybe_daily_summary(current_time, equity, drawdown)

    def _maybe_daily_summary(self, now: datetime, equity: float, drawdown: float) -> None:
        if not self._state_file:  # seulement en dry-run / réel
            return
        today = now.date().isoformat()
        if self._state.get("last_summary_date") == today or now.hour < DAILY_SUMMARY_HOUR_UTC:
            return
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        closed = Trade.get_trades_proxy(is_open=False, close_date=day_start)
        wins = [t for t in closed if (t.close_profit_abs or 0) > 0]
        pnl = sum((t.close_profit_abs or 0) for t in closed)
        n_open = len(Trade.get_trades_proxy(is_open=True))
        mode = "RÉEL" if self.dp.runmode == RunMode.LIVE else "DRY-RUN"
        self._notify(
            f"📊 Bilan du {today} ({mode})\n"
            f"Trades clôturés : {len(closed)} ({len(wins)} gagnants, "
            f"{len(closed) - len(wins)} perdants)\n"
            f"Résultat net du jour : {pnl:+.3f} USDT\n"
            f"Équité : {equity:.2f} USDT | plus haut : {self._state['peak_equity']:.2f} USDT | "
            f"drawdown : {drawdown:.1%}\n"
            f"Trades ouverts : {n_open}"
            + ("\n⛔ Coupe-circuit actif" if self._state.get("tripped") else "")
        )
        self._state["last_summary_date"] = today
        self._save_state()

    # ------------------------------------------------------------------------------------
    # Indicateurs
    # ------------------------------------------------------------------------------------
    @informative("1h")
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Filtre de tendance de fond : on évite d'acheter les baisses dans un marché en chute libre
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["bb_mid"] = dataframe["close"].rolling(20).mean()
        dataframe["bb_std"] = dataframe["close"].rolling(20).std(ddof=0)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["rsi_fast"] = ta.RSI(dataframe, timeperiod=4)
        dataframe["vol_mean"] = dataframe["volume"].rolling(20).mean()
        # Variation sur les 3 dernières bougies (15 min) : détecte la chute "brutale"
        dataframe["drop_15m"] = dataframe["close"] / dataframe["close"].shift(3) - 1
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bb_lower = dataframe["bb_mid"] - self.buy_bb_k.value * dataframe["bb_std"]

        cond = (
            (dataframe["close"] < bb_lower)
            & (dataframe["rsi_fast"] < self.buy_rsi_fast.value)
            & (dataframe["rsi"] < self.buy_rsi.value)
            & (dataframe["drop_15m"] < -self.buy_drop.value)
            & (dataframe["volume"] > dataframe["vol_mean"] * self.buy_vol_mult.value)
            & (dataframe["volume"] > 0)
        )
        if self.buy_trend_guard.value:
            # tolère jusqu'à -3 % sous l'EMA200 1h, et pas de RSI 1h en capitulation totale
            cond &= (dataframe["close_1h"] > dataframe["ema200_1h"] * 0.97)
            cond &= (dataframe["rsi_1h"] > 25)

        dataframe.loc[cond, ["enter_long", "enter_tag"]] = (1, "dip_bb_rsi_vol")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe

    # ------------------------------------------------------------------------------------
    # Garde-fous d'entrée et sorties personnalisées
    # ------------------------------------------------------------------------------------
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                            side: str, **kwargs) -> bool:
        if getattr(self, "_live_blocked", False):
            return False
        if getattr(self, "_state", {}).get("tripped"):
            return False
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs):
        if getattr(self, "_state", {}).get("tripped"):
            return "circuit_breaker"
        minutes = (current_time - trade.open_date_utc).total_seconds() / 60
        if minutes >= self.sell_timeout.value:
            return "timeout"
        return None
