#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Walk-forward pour ScalpDip (à lancer DANS le conteneur Freqtrade, voir README §6).

Principe (anti sur-optimisation) :
    |--- entraînement (hyperopt, N mois) ---|--- test (1 mois, jamais vu) ---|
                 |--- entraînement ---|--- test ---|           (on décale d'1 mois)
                              ...
  - Les paramètres sont optimisés UNIQUEMENT sur la fenêtre d'entraînement.
  - Ils sont ensuite appliqués tels quels sur le mois suivant (hors échantillon).
  - Le rapport final ne contient QUE les résultats des fenêtres de test, enchaînés
    (le capital de fin d'un mois de test est le capital de départ du suivant).

Usage (depuis le dossier scalping-bot/ sur l'hôte) :
  docker compose run --rm --entrypoint python freqtrade \
      /freqtrade/user_data/scripts/walkforward.py --download \
      --start 2025-07-01 --end 2026-11-01 --train-months 3 --epochs 300
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

UD = Path(os.environ.get("FT_USERDIR", "/freqtrade/user_data"))
CONFIGS = ["--config", str(UD / "config.json"), "--config", str(UD / "config.backtest.json")]
STRATEGY = "ScalpDip"
PARAMS_FILE = UD / "strategies" / f"{STRATEGY}.json"
RESULTS_DIR = UD / "backtest_results"
OUT_DIR = UD / "walkforward"
START_BALANCE = 21.0


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def tr(a: date, b: date) -> str:
    return f"{a:%Y%m%d}-{b:%Y%m%d}"


def run(cmd: list[str]) -> None:
    print("\n$ " + " ".join(cmd), flush=True)
    res = subprocess.run(cmd)
    if res.returncode != 0:
        sys.exit(f"Commande en échec (code {res.returncode})")


def latest_result() -> Path:
    from freqtrade.data.btanalysis import get_latest_backtest_filename
    return RESULTS_DIR / get_latest_backtest_filename(RESULTS_DIR)


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float(((peak - equity) / peak).max())


def btc_return(a: date, b: date, datadir: Path) -> float:
    from freqtrade.configuration import TimeRange
    from freqtrade.data.history import load_pair_history
    df = load_pair_history("BTC/USDT", "5m", datadir, timerange=TimeRange.parse_timerange(tr(a, b)))
    if df.empty:
        return float("nan")
    return float(df["close"].iloc[-1] / df["open"].iloc[0] - 1)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2025-07-01", help="début de la 1re fenêtre d'entraînement")
    p.add_argument("--end", default="2026-11-01", help="fin de la dernière fenêtre de test")
    p.add_argument("--train-months", type=int, default=3)
    p.add_argument("--test-months", type=int, default=1)
    p.add_argument("--epochs", type=int, default=300)
    p.add_argument("--loss", default="SharpeHyperOptLossDaily")
    p.add_argument("--fee", default="0.0015", help="frais+slippage par ordre (0.0015 = 0,1 %% + 0,05 %%)")
    p.add_argument("--jobs", default="-1")
    p.add_argument("--download", action="store_true", help="télécharger les données avant")
    p.add_argument("--skip-hyperopt", action="store_true",
                   help="tester les paramètres par défaut / actuels sans optimiser")
    p.add_argument("--no-detail", action="store_true",
                   help="ne pas utiliser les bougies 1m pour simuler l'intérieur des bougies 5m")
    a = p.parse_args()

    start = date.fromisoformat(a.start)
    end = date.fromisoformat(a.end)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    datadir = UD / "data" / "binance"

    if a.download:
        # 30 jours de marge avant le début pour les indicateurs (EMA200 en 1h)
        run(["freqtrade", "download-data", *CONFIGS, "--timeframes", "1m", "5m", "1h",
             "--timerange", f"{start - timedelta(days=30):%Y%m%d}-{end:%Y%m%d}"])

    if PARAMS_FILE.exists() and not a.skip_hyperopt:
        shutil.copy(PARAMS_FILE, OUT_DIR / f"{STRATEGY}.json.avant_walkforward")

    windows = []
    t0 = start
    while True:
        tr_a, tr_b = t0, add_months(t0, a.train_months)
        te_a, te_b = tr_b, add_months(tr_b, a.test_months)
        if te_b > end:
            break
        windows.append((tr_a, tr_b, te_a, te_b))
        t0 = add_months(t0, a.test_months)
    if not windows:
        sys.exit("Période trop courte pour une seule fenêtre entraînement+test.")

    manifest = []
    for i, (tr_a, tr_b, te_a, te_b) in enumerate(windows, 1):
        print(f"\n===== Fenêtre {i}/{len(windows)} : train {tr(tr_a, tr_b)} | test {tr(te_a, te_b)} =====")
        if not a.skip_hyperopt:
            run(["freqtrade", "hyperopt", *CONFIGS, "--strategy", STRATEGY,
                 "--hyperopt-loss", a.loss, "--spaces", "buy", "sell",
                 "--epochs", str(a.epochs), "--timerange", tr(tr_a, tr_b),
                 "--fee", a.fee, "--enable-protections", "-j", a.jobs, "--min-trades", "20"])
            if PARAMS_FILE.exists():
                shutil.copy(PARAMS_FILE, OUT_DIR / f"params_window{i:02d}.json")
        bt = ["freqtrade", "backtesting", *CONFIGS, "--strategy", STRATEGY,
              "--timerange", tr(te_a, te_b), "--fee", a.fee, "--enable-protections",
              "--export", "trades", "--cache", "none"]
        if not a.no_detail:
            bt += ["--timeframe-detail", "1m"]
        run(bt)
        manifest.append({"window": i, "train": tr(tr_a, tr_b), "test": tr(te_a, te_b),
                         "test_start": te_a.isoformat(), "test_end": te_b.isoformat(),
                         "result": str(latest_result())})
        (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

    report(manifest, datadir)


def report(manifest: list[dict], datadir: Path) -> None:
    from freqtrade.data.btanalysis import load_backtest_data

    rows, all_trades, curve = [], [], []
    growth, btc_growth = 1.0, 1.0
    for w in manifest:
        trades = load_backtest_data(Path(w["result"]), strategy=STRATEGY)
        a, b = date.fromisoformat(w["test_start"]), date.fromisoformat(w["test_end"])
        pnl = float(trades["profit_abs"].sum()) if len(trades) else 0.0
        g = 1 + pnl / START_BALANCE
        if len(trades):
            t = trades.sort_values("close_date")
            eq = growth * (START_BALANCE + t["profit_abs"].cumsum()) / START_BALANCE
            curve.append(pd.Series(eq.values, index=t["close_date"].values))
            all_trades.append(t)
        growth *= g
        btc = btc_return(a, b, datadir)
        btc_growth *= (1 + btc) if btc == btc else 1
        rows.append({"test": w["test"], "trades": len(trades),
                     "win_rate": (trades["profit_abs"] > 0).mean() if len(trades) else float("nan"),
                     "profit_%": (g - 1) * 100, "btc_hold_%": btc * 100})

    T = pd.concat(all_trades) if all_trades else pd.DataFrame(columns=["profit_abs", "profit_ratio"])
    wins = T[T["profit_abs"] > 0]
    losses = T[T["profit_abs"] <= 0]
    n = len(T)
    wr = len(wins) / n if n else 0.0
    avg_w = wins["profit_ratio"].mean() * 100 if len(wins) else 0.0
    avg_l = losses["profit_ratio"].mean() * 100 if len(losses) else 0.0
    be = abs(avg_l) / (avg_w + abs(avg_l)) if (avg_w + abs(avg_l)) else float("nan")
    equity = pd.concat([pd.Series([1.0])] + curve, ignore_index=True) if curve else pd.Series([1.0])
    mdd = max_drawdown(equity)
    pf = wins["profit_abs"].sum() / abs(losses["profit_abs"].sum()) if len(losses) and losses["profit_abs"].sum() else float("inf")

    lines = [
        "# Walk-forward ScalpDip — résultats HORS ÉCHANTILLON uniquement", "",
        f"Fenêtres de test : {len(manifest)} ({manifest[0]['test_start']} → {manifest[-1]['test_end']})", "",
        "| Indicateur | Valeur |", "|---|---|",
        f"| Nombre de trades | {n} |",
        f"| Win rate | {wr:.1%} |",
        f"| Gain moyen (net de frais) | {avg_w:+.2f} % |",
        f"| Perte moyenne (nette de frais) | {avg_l:+.2f} % |",
        f"| Win rate de break-even (avec ces gain/perte moyens) | {be:.1%} |",
        f"| Profit factor | {pf:.2f} |",
        f"| Profit net cumulé (après frais+slippage) | {(growth - 1) * 100:+.2f} % "
        f"({START_BALANCE:.0f} → {START_BALANCE * growth:.2f} USDT) |",
        f"| Drawdown max | {mdd:.1%} |",
        f"| Buy & hold BTC sur les mêmes périodes | {(btc_growth - 1) * 100:+.2f} % |", "",
    ]
    if n and "exit_reason" in T:
        lines += ["## Raisons de sortie", "", "| Raison | Trades | Profit moyen |", "|---|---|---|"]
        for r, g in T.groupby("exit_reason"):
            lines.append(f"| {r} | {len(g)} | {g['profit_ratio'].mean() * 100:+.2f} % |")
        lines.append("")
    lines += ["## Détail par mois de test", "",
              "| Mois de test | Trades | Win rate | Profit stratégie | BTC hold |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['test']} | {r['trades']} | {r['win_rate']:.1%} | "
                     f"{r['profit_%']:+.2f} % | {r['btc_hold_%']:+.2f} % |")
    out = "\n".join(lines)
    (OUT_DIR / "report.md").write_text(out)
    print("\n" + out + f"\n\nRapport écrit dans {OUT_DIR / 'report.md'}")
    print(f"Les paramètres actuellement dans {PARAMS_FILE.name} sont ceux de la DERNIÈRE fenêtre "
          "d'entraînement : ce sont ceux qu'utilisera le bot.")


if __name__ == "__main__":
    main()
