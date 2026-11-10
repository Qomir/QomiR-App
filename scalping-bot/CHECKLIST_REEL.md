# ✅ Checklist avant passage en argent réel

Ne passez en réel que si **toutes** les cases sont cochées. Une seule case non cochée = on reste
en dry-run.

## A. Validation de la stratégie

- [ ] Le walk-forward (README §6) a été lancé sur **≥ 12 mois de test hors échantillon**.
- [ ] Dans `user_data/walkforward/report.md` :
  - [ ] le profit net est **positif** après frais et slippage (`--fee 0.0015`) ;
  - [ ] le win rate dépasse le **win rate de break-even** d'au moins **5 points** ;
  - [ ] il y a au moins **200 trades** (en dessous, le résultat peut être de la chance) ;
  - [ ] le drawdown max est **< 25 %** ;
  - [ ] la majorité des mois de test sont positifs, pas un seul gros mois qui compense tout ;
  - [ ] vous avez comparé honnêtement au buy & hold BTC.
- [ ] Les paramètres `params_windowXX.json` sont **relativement stables** d'une fenêtre à l'autre.

## B. Validation en dry-run

- [ ] Le bot a tourné **au moins 2 à 4 semaines** en dry-run, sans interruption anormale.
- [ ] Le win rate et le profit moyen du dry-run sont **cohérents** avec le backtest de la même
      période. Pour le vérifier, lancez un backtest sur ces dates précises et comparez.
- [ ] Vous avez reçu sur Telegram les trades, les bilans quotidiens et au moins un message de
      protection.
- [ ] Vous avez testé le coupe-circuit. Pour cela, mettez temporairement
      `CIRCUIT_BREAKER_DRAWDOWN = 0.003` dans une **copie** de la stratégie lancée en backtest :
      vous devez voir « COUPE-CIRCUIT DÉCLENCHÉ ». Remettez ensuite 0.30.
- [ ] Vous avez testé un redémarrage (`docker compose restart`) et un reboot du serveur
      (`sudo reboot`) : le bot repart tout seul.

## C. Compte Binance

- [ ] La 2FA (application d'authentification, pas SMS) est active sur le compte.
- [ ] Le compte spot ne contient **que** ce que vous acceptez de perdre : 21 USDT, plus 5 à 6 USDT
      de BNB si vous payez les frais en BNB. Le reste est sur un autre compte ou en sous-compte.
- [ ] (Optionnel, recommandé) « Payer les frais avec BNB » est activé et le BNB est acheté (README §1.4).
- [ ] Clé API créée selon le README §9 :
  - [ ] lecture ✅ et trading spot ✅ ;
  - [ ] **retraits ❌** ;
  - [ ] futures ❌, marge ❌, transfert universel ❌ ;
  - [ ] **restreinte à l'IP du serveur** ✅ ;
  - [ ] aucun compte marge ouvert.
- [ ] La clé est **uniquement** dans `.env`. Vérifiez avec `git status` qu'il n'apparaît pas, et
      `ls -l .env` doit afficher `-rw-------`.

## D. Modifications manuelles (dans cet ordre)

1. [ ] Arrêter le bot : `docker compose down`.
2. [ ] `.env` :
   - [ ] remplir `FREQTRADE__EXCHANGE__KEY` et `FREQTRADE__EXCHANGE__SECRET` ;
   - [ ] décommenter `CONFIRM_LIVE_TRADING=OUI_JE_COMPRENDS_LES_RISQUES`.
3. [ ] `user_data/config.json` :
   - [ ] `"dry_run": false` ;
   - [ ] ajouter `"available_capital": 21,` sous `dry_run_wallet`. Cela plafonne le capital
         utilisé par le bot, même si le compte contient plus. Les gains restent réinvestis ;
   - [ ] si les frais sont payés en BNB : `"fee": 0.00075` (sinon, laissez la ligne).
4. [ ] `docker-compose.yml` : remplacer `tradesv3.dryrun.sqlite` par **`tradesv3.live.sqlite`**,
       pour ne jamais mélanger l'historique papier et réel.
5. [ ] Vérifier la clé sans trader :
       `docker compose run --rm freqtrade list-markets --config user_data/config.json --quote USDT -1 | head`
6. [ ] Démarrer : `docker compose up -d`, puis `docker compose logs -f`.
7. [ ] Contrôler les logs et Telegram :
   - [ ] le message de démarrage **ne dit plus** « Dry run » ;
   - [ ] **aucune** ligne `MODE RÉEL détecté mais CONFIRM_LIVE_TRADING...`. Si elle apparaît, la
         confirmation n'est pas prise en compte et aucun trade ne sera pris ;
   - [ ] `/balance` sur Telegram affiche bien le solde réel.

## E. Premières semaines en réel

- [ ] Au premier trade, vérifiez dans l'application Binance que l'ordre **stop-loss** est bien
      présent dans les « Ordres ouverts » (`stoploss_on_exchange`).
- [ ] Consultez le bilan quotidien Telegram chaque jour.
- [ ] Fixez-vous une règle d'arrêt **avant** de commencer : par exemple, si après 100 trades
      réels le win rate est sous le break-even, on arrête.
- [ ] En cas de coupe-circuit : **ne réarmez pas à chaud.** Analysez les trades perdants et
      relancez un walk-forward. Ne repartez éventuellement qu'en dry-run.

## Retour en dry-run à tout moment

Faites `docker compose down`, remettez `"dry_run": true`, remettez `tradesv3.dryrun.sqlite` et
commentez `CONFIRM_LIVE_TRADING`, puis `docker compose up -d`. En cas d'urgence, envoyez
`/forceexit all` puis `/stop` sur Telegram.
