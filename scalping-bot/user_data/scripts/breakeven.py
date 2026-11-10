#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calcul du win rate minimum pour être rentable (aucune dépendance, lançable partout) :
    python3 user_data/scripts/breakeven.py

Hypothèses :
  - take-profit exprimé NET des frais (comme minimal_roi dans Freqtrade),
  - stop-loss exprimé en variation de PRIX (comme stoploss dans Freqtrade) : la perte
    nette = stop + frais aller-retour,
  - le slippage pénalise à la fois les gains et les pertes.
Formule : win_rate_min = perte / (gain + perte)
"""

FEES = {"Sans BNB (0,1 %/ordre)": 0.10, "Avec BNB (0,075 %/ordre)": 0.075}
SLIPPAGE = 0.05          # % par ordre (estimation prudente sur paires très liquides)
TPS = [0.5, 0.75, 1.0]   # take-profit NET des frais, en %
SLS = [1.0, 1.5, 2.0]    # stop-loss en % de prix

for label, fee in FEES.items():
    rt = 2 * fee
    print(f"\n=== {label} — frais aller-retour {rt:.2f} %, slippage {SLIPPAGE:.2f} %/ordre ===")
    print(f"{'TP net':>7} {'hausse prix requise':>20} {'SL prix':>8} {'perte nette':>12} {'win rate min':>13}")
    for tp in TPS:
        for sl in SLS:
            win = tp - 2 * SLIPPAGE
            loss = sl + rt + 2 * SLIPPAGE
            print(f"{tp:>6.2f}% {tp + rt:>19.2f}% {sl:>7.1f}% {loss:>11.2f}% {loss / (win + loss):>12.1%}")
