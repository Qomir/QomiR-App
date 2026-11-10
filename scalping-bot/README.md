# ScalpDip : bot de scalping Binance spot (Freqtrade + Docker, 100 % gratuit)

> ⚠️ **Avertissement.** Ce bot peut perdre tout votre capital. Il démarre **obligatoirement en
> dry-run** (paper trading). Rien ici n'est un conseil en investissement. Lisez d'abord le
> **§1, « La vérité sur les chiffres »**.

---

## Sommaire

1. [La vérité sur les chiffres (à lire en premier)](#1-la-vérité-sur-les-chiffres)
2. [Ce que fait le bot](#2-ce-que-fait-le-bot)
3. [Structure du projet](#3-structure-du-projet)
4. [Installation : Oracle Cloud Always Free (ARM) ou votre PC](#4-installation)
5. [Configuration : `.env`, Telegram, FreqUI](#5-configuration)
6. [Backtest et walk-forward (validation)](#6-backtest-et-walk-forward)
7. [Lancer le bot en dry-run](#7-lancer-le-bot-en-dry-run)
8. [Suivi : Telegram, FreqUI par tunnel SSH, logs](#8-suivi)
9. [Clé API Binance sécurisée](#9-clé-api-binance)
10. [Passage en réel](#10-passage-en-réel)
11. [Commandes utiles et dépannage](#11-commandes-utiles)

---

## 1. La vérité sur les chiffres

### 1.1 Les frais mangent une grosse partie du gain visé

Binance prélève 0,1 % par ordre, soit **0,2 % par aller-retour** (0,15 % si les frais sont payés en BNB).
Pour gagner +0,5 % **net**, le prix doit monter d'environ **+0,7 %**. Sur un trade à +0,5 % net,
vous avez donc déjà payé **0,2 % de frais, soit 40 % du gain visé**.

### 1.2 Win rate minimum pour être rentable

Formule : `win rate minimum = perte nette / (gain net + perte nette)`.
Hypothèses : frais 0,1 %/ordre et slippage 0,05 %/ordre. Pour refaire le calcul :
`python3 user_data/scripts/breakeven.py`.

| TP net visé | Hausse de prix nécessaire | Stop-loss (prix) | Perte nette réelle | **Win rate minimum** |
|---|---|---|---|---|
| +0,50 % | +0,70 % | -1,0 % | -1,30 % | **76,5 %** |
| +0,50 % | +0,70 % | -1,5 % | -1,80 % | **81,8 %** |
| +0,75 % | +0,95 % | -1,5 % | -1,80 % | **73,5 %** |
| +1,00 % | +1,20 % | -1,0 % | -1,30 % | **59,1 %** |
| +1,00 % | +1,20 % | -1,5 % | -1,80 % | **66,7 %** |

Les réglages par défaut du bot (TP dégressif de +1 % à +0,5 %, stop -1,5 %) exigent
**environ 70 à 80 % de trades gagnants** pour seulement couvrir les frais. C'est atteignable sur
le papier : une stratégie d'achat de rebond gagne souvent plus de 70 % de ses trades. Mais la
marge d'erreur est minuscule. **Quelques points de win rate en moins suffisent à rendre le bot perdant.**

### 1.3 Pourquoi ce que vous demandez est difficile, voire perdant

* **« Beaucoup de petits trades » est le scénario qui profite le plus à Binance.** Chaque trade
  coûte 0,2 % quoi qu'il arrive. Les scalpeurs professionnels ne paient presque pas de frais,
  voire touchent des rebates de market-maker. Un particulier au niveau VIP 0 part avec un
  handicap structurel.
* **Le scalping sur bougies de 1 minute est mathématiquement très défavorable.** Une bougie 1m
  sur BTC bouge typiquement de 0,05 à 0,2 %, l'ordre de grandeur des frais. Le bot détecte donc
  ses signaux en **5m**. Les données **1m** servent à simuler précisément, en backtest, l'ordre
  dans lequel stop et take-profit sont touchés (`--timeframe-detail 1m`). C'est un choix délibéré.
* **Les ordres limite ne sont pas toujours exécutés.** En backtest, Freqtrade suppose que l'ordre
  limite d'achat est exécuté au prix de clôture de la bougie. En réel, quand le prix rebondit
  immédiatement, l'ordre ne s'exécute pas : vous ratez les meilleurs trades. Quand il continue de
  chuter, l'ordre s'exécute : vous prenez les pires. Ce phénomène s'appelle la **sélection adverse**.
  C'est la raison n° 1 pour laquelle le réel fait moins bien que le backtest. D'où le slippage
  ajouté et l'étape de dry-run obligatoire.
* **Avec 21 USDT, les montants absolus sont dérisoires.** Scénario optimiste : +0,05 % net par
  trade en moyenne, 10 trades par jour, ~50 % du capital par trade. Cela donne environ
  **+0,25 % par jour, soit +1 à +2 USDT par mois**. Un mois moyen en scalping, c'est plutôt
  −2 à +1 USDT. **Ce bot est un outil d'apprentissage, pas une source de revenus.** Avec ce
  capital, faire « croître » vite les 20 € est irréaliste sans un risque de ruine très élevé.
* **Le minimum d'ordre Binance (~5 USDT) borne le bot.** Avec la marge de sécurité de Freqtrade,
  une mise doit faire environ 5,4 USDT. En dessous d'environ 11 USDT de capital, le bot ne peut
  plus tenir 2 trades. En dessous d'environ 5,5 USDT, il ne peut plus trader du tout. Le
  coupe-circuit à -30 % (environ 14,7 USDT) se déclenche avant.

### 1.4 Payer les frais en BNB : est-ce rentable ?

**Oui en réel, mais pas tout de suite.**

| | Sans BNB | Avec BNB |
|---|---|---|
| Frais aller-retour | 0,20 % | 0,15 % |
| Hausse nécessaire pour +0,5 % net | +0,70 % | +0,65 % |
| Économie par trade de 10 USDT | – | 0,005 USDT |
| Économie à 10 trades/jour | – | ≈ 1,5 USDT/mois (≈ 7 % du capital/mois) |

* ✅ **Pour :** les frais baissent de 25 %, soit **10 % de votre objectif de +0,5 %** récupérés à
  chaque trade. C'est énorme à cette échelle. Autre avantage : les frais ne sont plus prélevés sur
  la crypto achetée, donc moins de « poussières » invendables.
* ❌ **Contre :** l'achat minimum de BNB est d'environ 5 USDT. Cela immobilise **≈ 24 % de votre
  capital** hors trading, exposé au cours du BNB. Il faut aussi surveiller ce solde et le
  recharger : 5 USDT de BNB couvrent environ 6 600 USDT de volume, soit environ un mois à
  10 trades par jour.
* **Recommandation :** en réel, activez « Payer les frais avec BNB » dans Binance et achetez pour
  5 à 6 USDT de BNB. La paire `BNB/USDT` est dans la blacklist pour que le bot n'y touche jamais.
  En dry-run, mettez `"fee": 0.00075` dans `config.json` pour simuler ce cas. Les backtests
  restent faits à 0,15 % par ordre (frais sans BNB + slippage), ce qui est volontairement pessimiste.

### 1.5 Résultats de backtest

**Je n'ai PAS pu exécuter le backtest sur les vraies données Binance** : l'environnement de
développement n'avait pas accès à l'API Binance. Je ne vous donne donc **aucun chiffre inventé**.

Ce qui a été vérifié dans Freqtrade 2026.10, sur données synthétiques :

* la stratégie se charge et produit des trades ;
* le backtest tourne avec `--timeframe-detail 1m`, les protections et les frais majorés ;
* l'hyperopt fonctionne et exporte bien les paramètres ;
* le coupe-circuit se déclenche, liquide les positions puis bloque toute nouvelle entrée ;
* le rapport walk-forward est généré correctement.

Les résultats sur données synthétiques n'ont **aucune valeur prédictive**. Les données étaient
fabriquées avec des rebonds artificiels, ce qui flatte la stratégie.

👉 **Le §6 vous fait générer les vrais résultats** sur plus d'un an de données Binance. Le rapport
contient tout ce que vous avez demandé : nombre de trades, win rate, gain et perte moyens,
win rate de break-even, profit net après frais et slippage, drawdown max, et comparaison avec le
buy & hold BTC. **Il ne porte que sur les périodes de test hors échantillon.**

**Règle de décision honnête :** si le rapport walk-forward ne montre pas à la fois un profit net
positif, un win rate supérieur au break-even de plusieurs points, au moins 200 trades et un
drawdown max inférieur à 25 %, **n'allez pas en réel**. C'est le résultat le plus probable pour une
stratégie de scalping, et ce serait la bonne décision.

---

## 2. Ce que fait le bot

| Élément | Implémentation |
|---|---|
| Marché | Binance **spot**, paires `/USDT`, sans levier ni short |
| Scan des paires | `VolumePairList` sur toutes les paires USDT : top 30 par volume 24h (≥ 20 M USDT), puis filtres âge ≥ 30 j, prix (1 tick ≤ 0,1 %), **spread < 0,1 %** et volatilité. On garde le top 15, rafraîchi toutes les 30 min. Stablecoins, jetons à levier et BNB sont exclus. |
| Signal d'entrée (5m) | Clôture **sous la bande de Bollinger basse** (k réglable) + **RSI(4) très bas** + RSI(14) bas + **chute de plus de X % en 15 min** + **volume > N × moyenne**. Garde-fou de tendance en 1h : pas d'achat si le prix est à plus de 3 % sous l'EMA200 1h ou si le RSI 1h est inférieur à 25. |
| Take-profit (net de frais) | +1 % pendant les 10 premières minutes, puis +0,75 % jusqu'à 20 min, puis +0,5 % |
| Stop-loss | -1,5 % de prix (≈ -1,7 % net), **posé directement chez Binance** en réel (`stoploss_on_exchange`), donc il protège même si le serveur tombe |
| Sortie forcée | Après `sell_timeout` minutes (60 par défaut, optimisé entre 20 et 180), quel que soit le résultat |
| Mise | `stake_amount: "unlimited"` : capital ÷ slots libres, recalculé à chaque trade. **Les gains sont réinvestis automatiquement** (intérêts composés). |
| Trades simultanés | 2 maximum |
| Protections Freqtrade | `CooldownPeriod`, `StoplossGuard` (global et par paire), `MaxDrawdown` (10 % sur 24h, pause de 12h), `LowProfitPairs` |
| **Coupe-circuit** | Si l'équité (réalisée + latente) tombe à **-30 % de son plus haut** : alerte Telegram, **liquidation de toutes les positions et plus aucune entrée**, même après redémarrage. L'état est stocké dans `user_data/scalpdip_state.*.json`. |
| Verrou réel | Même avec `dry_run: false`, aucune entrée n'est prise sans `CONFIRM_LIVE_TRADING=OUI_JE_COMPRENDS_LES_RISQUES` dans `.env` |
| API Binance | Websockets activés (`enable_ws`) ; limiteur de requêtes ccxt actif (`enableRateLimit`, 200 ms) |
| Notifications | Telegram : achats et ventes exécutés, protections, bilan quotidien vers 20h UTC, coupe-circuit |
| Résilience | `restart: unless-stopped` dans Docker, et Docker activé au démarrage du système |

---

## 3. Structure du projet

```
scalping-bot/
├── docker-compose.yml          # service Freqtrade, redémarrage auto, FreqUI sur 127.0.0.1 uniquement
├── .env.example                # modèle des secrets -> copier en .env (non versionné)
├── .gitignore
├── README.md                   # ce fichier
├── CHECKLIST_REEL.md           # à valider AVANT de passer en argent réel
├── scripts/
│   └── install_ubuntu.sh       # installe Docker, pare-feu, mises à jour auto, NTP
└── user_data/
    ├── config.json             # configuration commentée (dry_run: true)
    ├── config.backtest.json    # surcouche backtest (liste de paires fixe)
    ├── strategies/ScalpDip.py  # la stratégie
    └── scripts/
        ├── walkforward.py      # walk-forward + rapport hors échantillon + comparaison BTC
        └── breakeven.py        # calcul du win rate minimum
```

---

## 4. Installation

### Option A : Oracle Cloud Always Free (recommandé, tourne 24h/24)

1. **Créer le compte** sur <https://www.oracle.com/cloud/free/>. Une carte bancaire est demandée
   pour vérification ; rien n'est débité tant que vous restez dans les ressources « Always Free ».
   - **Région d'origine : choisissez Paris, Marseille ou Frankfurt.** Ce choix est définitif.
     **Évitez les régions USA** : Binance.com bloque les IP américaines.
2. **Créer l'instance** : *Compute → Instances → Create instance*.
   - Image : **Canonical Ubuntu 24.04** (aarch64).
   - Shape : *Change shape → Ampere → **VM.Standard.A1.Flex*** avec 2 OCPU et 12 Go de RAM.
     Ça reste gratuit jusqu'à 4 OCPU / 24 Go au total.
   - Réseau : laissez « Assign a public IPv4 address » coché.
   - SSH : *Generate a key pair*. **Téléchargez la clé privée** et gardez-la précieusement.
   - En cas d'erreur « *Out of capacity* », réessayez plus tard ou changez d'Availability Domain.
     C'est fréquent sur les instances ARM gratuites.
3. **Ne pas ouvrir de port** dans la *Security List* : seul le port 22 (SSH) doit être ouvert,
   c'est le réglage par défaut. FreqUI passe par un tunnel SSH.
4. **Se connecter** depuis votre PC (PowerShell, terminal macOS ou Linux) :
   ```bash
   chmod 600 ~/Téléchargements/ssh-key-*.key        # Linux/macOS uniquement
   ssh -i ~/Téléchargements/ssh-key-XXXX.key ubuntu@IP_PUBLIQUE
   ```
5. **Installer le projet** sur la VM :
   ```bash
   git clone https://github.com/Qomir/QomiR-App.git
   cd QomiR-App/scalping-bot
   bash scripts/install_ubuntu.sh
   exit            # puis reconnectez-vous en SSH (pour le groupe docker)
   ```
   Si le dépôt est privé : `git clone` demandera un *Personal Access Token* GitHub (en lecture
   seule) à la place du mot de passe. Vous pouvez aussi copier le dossier depuis votre PC :
   `scp -i cle.key -r scalping-bot ubuntu@IP_PUBLIQUE:~/`.
6. **Noter l'IP publique** pour la clé API Binance : `curl -4 ifconfig.me`. L'IP éphémère est
   conservée quand l'instance est arrêtée puis redémarrée. Elle n'est perdue que si l'instance
   est supprimée.

> ⚠️ **Récupération des instances inactives.** Oracle peut récupérer une instance Always Free
> qu'il juge « inactive » (CPU, réseau et mémoire sous 20 % pendant 7 jours). Un bot Freqtrade
> consomme très peu de ressources. Pour éviter ce risque, passez le compte en *Pay As You Go* :
> les ressources Always Free restent gratuites. Configurez alors une **alerte budgétaire à
> 1 €** dans *Billing → Budgets* pour être prévenu au moindre coût.

### Option B : votre PC

* **Windows** : installez *Docker Desktop* (backend WSL2), puis activez *Start Docker Desktop when
  you sign in*. Installez *Git for Windows*.
* **Linux** : `bash scripts/install_ubuntu.sh` fonctionne sur Ubuntu et Debian.
* **macOS** : Docker Desktop.
* Ensuite : `git clone https://github.com/Qomir/QomiR-App.git` puis `cd QomiR-App/scalping-bot`.
* Limites :
  - le PC doit rester allumé et **ne jamais se mettre en veille** ;
  - votre IP domestique change souvent, ce qui complique la restriction IP de la clé Binance (§9).

---

## 5. Configuration

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

### 5.1 Telegram (gratuit)

1. Dans Telegram, ouvrez **@BotFather**, tapez `/newbot` et choisissez un nom. Copiez le
   **token** dans `FREQTRADE__TELEGRAM__TOKEN`.
2. Envoyez un message quelconque à **votre** nouveau bot. Sans ça, il ne pourra pas vous écrire.
3. Ouvrez **@userinfobot** : il vous donne votre **id**, à copier dans `FREQTRADE__TELEGRAM__CHAT_ID`.

### 5.2 FreqUI / API

Générez les secrets :

```bash
echo "PASSWORD=$(openssl rand -base64 18)"
echo "JWT=$(openssl rand -hex 32)"
echo "WS=$(openssl rand -hex 16)"
```

Collez-les dans `FREQTRADE__API_SERVER__PASSWORD`, `FREQTRADE__API_SERVER__JWT_SECRET_KEY` et
`FREQTRADE__API_SERVER__WS_TOKEN`. **Sans mot de passe, le bot refuse de démarrer** : c'est voulu.

### 5.3 Clés Binance

En dry-run, **laissez-les vides**. Les données de marché sont publiques.

---

## 6. Backtest et walk-forward

Toutes les commandes se lancent dans `scalping-bot/`.

### 6.1 Méthode

```
|— entraînement 3 mois (hyperopt) —|— test 1 mois —|
            |— entraînement 3 mois —|— test 1 mois —|        (décalage d'un mois)
                         ...
```

* Les paramètres d'entrée et le timeout sont optimisés **uniquement** sur l'entraînement.
* Ils sont ensuite appliqués **sans modification** au mois suivant, que la stratégie n'a jamais vu.
* Le rapport n'additionne **que les mois de test**, enchaînés en intérêts composés.
* Le take-profit et le stop-loss ne sont **pas** optimisés. Ils restent fixés à vos objectifs,
  pour limiter la sur-optimisation.
* Frais : `--fee 0.0015` par ordre, soit 0,1 % de frais Binance + 0,05 % de slippage estimé.
* Simulation intra-bougie sur 1m : `--timeframe-detail 1m`.
* Les protections sont activées : `--enable-protections`.

### 6.2 Lancer

Avec 16 mois de données, on obtient 13 mois de test hors échantillon :

```bash
docker compose pull
docker compose run --rm --entrypoint python freqtrade \
    /freqtrade/user_data/scripts/walkforward.py --download \
    --start 2025-07-01 --end 2026-11-01 --train-months 3 --epochs 300
```

* Le téléchargement (1m, 5m et 1h, 15 paires) occupe environ 0,5 à 1 Go et prend 15 à 60 min.
* L'hyperopt demande plusieurs heures au total sur 2 à 4 OCPU. Pour un premier essai rapide,
  utilisez `--epochs 80`. Pour tester les paramètres par défaut sans optimisation, utilisez
  `--skip-hyperopt`.
* Lancez-le dans `tmux` pour pouvoir fermer la session SSH : `sudo apt install tmux`, puis `tmux`,
  puis la commande. Détachez avec `Ctrl+B` puis `D`, et revenez avec `tmux attach`.

### 6.3 Lire le résultat

Le rapport est écrit dans `user_data/walkforward/report.md`. Il contient :

* les indicateurs globaux : nombre de trades, win rate, gain et perte moyens, **win rate de
  break-even**, profit factor, profit net, drawdown max, **buy & hold BTC** ;
* la répartition par raison de sortie (roi, stop_loss, timeout) ;
* le détail mois par mois, stratégie contre BTC.

Les paramètres de chaque fenêtre sont gardés dans `user_data/walkforward/params_windowXX.json`.
**S'ils changent énormément d'un mois à l'autre, la stratégie n'a probablement pas d'avantage
stable.** À la fin, `user_data/strategies/ScalpDip.json` contient les paramètres de la dernière
fenêtre : ce sont ceux que le bot utilisera.

Vous pouvez aussi lancer un backtest simple, par exemple :

```bash
docker compose run --rm freqtrade backtesting \
  --config user_data/config.json --config user_data/config.backtest.json \
  --strategy ScalpDip --timerange 20260601-20261101 --fee 0.0015 \
  --timeframe-detail 1m --enable-protections
```

> Biais à connaître :
> - **biais du survivant** : la liste fixe de 15 paires correspond aux grosses paires
>   d'aujourd'hui ;
> - en backtest, les ordres limite sont supposés **toujours exécutés** (voir §1.3).
>
> Le réel sera **moins bon** que le backtest.

---

## 7. Lancer le bot en dry-run

```bash
docker compose up -d
docker compose logs -f --tail 100       # Ctrl+C pour quitter les logs (le bot continue)
```

Vous devez recevoir le message de démarrage sur Telegram, avec la mention *Dry run*. Laissez
tourner **au moins 2 à 4 semaines** et comparez avec le backtest de la même période.

---

## 8. Suivi

### Telegram

Commandes utiles :

* `/status` et `/status table` : trades ouverts ;
* `/profit` : profit cumulé ;
* `/daily` : profit par jour ;
* `/balance` : solde ;
* `/performance` : résultats par paire ;
* `/stopentry` : plus aucune nouvelle entrée, les trades en cours se terminent normalement ;
* `/forceexit all` : vend tout ;
* `/stop` et `/start` : arrête et relance le bot.

Messages automatiques : achats et ventes exécutés, protections déclenchées, **bilan quotidien**
vers 20h UTC, et **🚨 alerte coupe-circuit**.

### FreqUI, uniquement via tunnel SSH

Le port 8080 n'est publié que sur `127.0.0.1` du serveur. Il est invisible depuis Internet.
Depuis votre PC :

```bash
ssh -i ~/chemin/cle.key -N -L 8080:127.0.0.1:8080 ubuntu@IP_PUBLIQUE
```

Ouvrez ensuite <http://localhost:8080>, avec l'utilisateur `freqtrader` et le mot de passe défini
dans `.env`. Fermez le tunnel avec `Ctrl+C`.

### Redémarrage automatique

* Si Freqtrade plante, Docker le relance (`restart: unless-stopped`).
* Si le serveur redémarre, Docker est activé au boot (`systemctl enable docker`) et relance
  le conteneur.
* Le coupe-circuit, le plus haut d'équité et le dernier bilan sont stockés dans
  `user_data/scalpdip_state.*.json`. Ils **survivent** aux redémarrages.

---

## 9. Clé API Binance

À créer **uniquement au moment de passer en réel**.

1. Binance (site web) → icône de profil → **Gestion des API** → **Créer une API** →
   **Générée par le système (HMAC)**. Nommez-la `freqtrade-scalpdip` et validez avec la 2FA.
2. Cliquez sur **Modifier les restrictions** :
   - ✅ **Activer la lecture** ;
   - ✅ **Activer le trading spot et sur marge**. N'ouvrez **pas** de compte marge : sans compte
     marge, ce droit ne permet que le spot ;
   - ❌ **Activer les retraits** : **JAMAIS** ;
   - ❌ Prêts sur marge, Futures, Options, Transfert universel : **décochés** ;
   - 🔒 **Restreindre l'accès aux adresses IP de confiance uniquement**, puis saisissez l'IP
     publique du serveur (`curl -4 ifconfig.me`).
3. Copiez la clé et le secret dans `.env` (`FREQTRADE__EXCHANGE__KEY` et `__SECRET`). Le secret ne
   s'affiche **qu'une fois**.
4. Sur PC avec une IP domestique dynamique : restreindre à l'IP casse la clé à chaque changement
   d'IP. Sans restriction, la clé reste utilisable depuis n'importe où si elle fuit. Binance peut
   aussi restreindre les clés non limitées par IP. C'est une raison de plus pour préférer le
   serveur Oracle.
5. Vérifiez que la clé fonctionne, **sans trader** :
   `docker compose run --rm freqtrade list-markets --config user_data/config.json --quote USDT -1 | head`

> Fiscalité (France) : un compte Binance doit être déclaré chaque année (formulaire **3916-bis**).
> Les échanges crypto→crypto, USDT compris, ne sont pas imposables. Seules les conversions en
> euros le sont. Gardez l'export de vos trades.

---

## 10. Passage en réel

👉 Suivez **`CHECKLIST_REEL.md`** point par point. Il faut trois actions manuelles distinctes :

1. `config.json` : `"dry_run": false` ;
2. `docker-compose.yml` : nouvelle base `tradesv3.live.sqlite` ;
3. `.env` : la clé API **et** la ligne de confirmation `CONFIRM_LIVE_TRADING=...`.

---

## 11. Commandes utiles

| Action | Commande |
|---|---|
| Démarrer / arrêter | `docker compose up -d` / `docker compose down` |
| Logs en direct | `docker compose logs -f --tail 100` |
| Mettre à jour Freqtrade | `docker compose pull && docker compose up -d` |
| Win rate minimum | `python3 user_data/scripts/breakeven.py` |
| Paires actuellement scannées | `docker compose run --rm freqtrade test-pairlist --config user_data/config.json` |
| Réarmer le coupe-circuit (après analyse !) | `docker compose down && rm user_data/scalpdip_state.dryrun.json && docker compose up -d` |

**Dépannage :**

* *« Timestamp for this request is outside of the recvWindow »* : l'horloge du serveur dérive.
  Lancez `sudo timedatectl set-ntp true`.
* *« 'password' is a required property »* : le `.env` n'est pas rempli (§5.2).
* *« Invalid API-key, IP, or permissions »* : l'IP du serveur n'est pas celle déclarée chez
  Binance, ou le droit trading spot n'est pas activé.
* Le bot ne prend aucun trade en réel : c'est normal tant que `CONFIRM_LIVE_TRADING` n'est pas
  renseigné (voir les logs). Sinon, le signal est simplement rare : c'est voulu, il attend de
  vraies chutes brutales.
