# PrecisVis — boutique pilotée par des agents IA

Ce dossier contient un système qui gère chaque jour la boutique Shopify **PrecisVis**
(tournevis électrique de précision) **sans intervention quotidienne** de votre part.
Vous recevez **un e-mail bilan chaque soir à 20h00 (heure de Paris)**.

> **Publication 100 % organique.** Le système ne crée **aucune** campagne payante. Il n'y a aucun
> code de publicité payante, et si quelqu'un met `paid_ads.enabled: true` ou un budget pub dans
> `config.yaml`, le système refuse de démarrer et vous prévient.

---

## Sommaire

1. [Ce que fait le système](#1-ce-que-fait-le-système)
2. [Ce qui reste entre vos mains](#2-ce-qui-reste-entre-vos-mains)
3. [Créer les comptes et récupérer les clés](#3-créer-les-comptes-et-récupérer-les-clés)
4. [Déployer sur GitHub (recommandé)](#4-déployer-sur-github-recommandé)
5. [Tester en simulation](#5-tester-en-simulation)
6. [Lire le bilan du soir](#6-lire-le-bilan-du-soir)
7. [Arrêt d'urgence](#7-arrêt-durgence)
8. [Régler le système (`config.yaml`)](#8-régler-le-système-configyaml)
9. [Alternative : serveur VPS avec cron](#9-alternative--serveur-vps-avec-cron)
10. [Conformité : à vérifier une fois](#10-conformité--à-vérifier-une-fois)
11. [Limites connues](#11-limites-connues)
12. [Pour les développeurs](#12-pour-les-développeurs)

---

## 1. Ce que fait le système

| Heure (Paris) | Agent | Ce qu'il fait |
|---|---|---|
| 07:00 | **Veille** | Analyse les publicités concurrentes (Bibliothèque publicitaire Meta) et les tendances TikTok/Reels, et transmet les angles qui marchent. Le lundi, il propose 1 à 3 produits complémentaires (20–60 € d'achat, **jamais de beauté**) en **brouillon**. |
| | **Catalogue** | Réécrit les fiches produit (SEO, bénéfices, FAQ) et ajoute les mentions légales. **Ne publie jamais** une fiche : il vous demande de valider. |
| | **Visuels IA** | Crée 6 images et 2 vidéos par jour, déclinées en 1:1, 4:5 et 9:16, **à partir des vraies photos du produit**. Chaque visuel est noté par l'IA ; s'il obtient moins de 7/10, il est refait (3 essais maximum). |
| | **Copywriting** | Écrit 3 variantes de texte par visuel et par réseau (TikTok, Facebook, Instagram). Les formulations interdites (fausse urgence, prix barrés, faux avis…) sont bloquées. |
| | **Publication** | Programme les publications organiques de la journée. |
| | **Commandes** | Vérifie que DSers transmet bien les commandes et les numéros de suivi, et repère les colis bloqués et les litiges de paiement. |
| | **SAV** | Lit la boîte support et répond seul aux questions simples. Il prépare les remboursements et les litiges, mais ne les traite **jamais** seul. |
| | **Analytics** | Calcule le chiffre d'affaires, les commandes, la marge et les statistiques des publications, puis désigne les visuels gagnants. |
| 12:30 et 18:30 | **Publication** | Publie sur la Page Facebook, Instagram (fil et Reels) et TikTok. |
| 20:00 | **Analytics + Reporting** | Calcule les chiffres du jour et vous envoie le bilan. |

Garde-fous automatiques :

- **Plafond de coût IA** : 5 €/jour et 120 €/mois par défaut. Une fois le plafond atteint, les agents s'arrêtent et vous le signalent.
- **Interrupteur d'arrêt** (`kill_switch`) : voir la section 7.
- Si un agent échoue, il est relancé 2 fois ; s'il échoue encore, le système passe à l'agent suivant et l'échec apparaît dans le bilan.
- Si une exécution entière échoue, un **e-mail d'alerte** part immédiatement.
- Toutes les clés restent dans les « secrets » GitHub, jamais dans le code.

## 2. Ce qui reste entre vos mains

Tout ce qui suit apparaît dans la rubrique **« À traiter »** du bilan :

- valider un **remboursement** (la réponse au client est déjà rédigée) ;
- répondre aux **litiges** et aux réclamations agressives ou juridiques ;
- **publier** un nouveau produit ou une fiche brouillon (après avoir vérifié le **marquage CE** auprès du fournisseur) ;
- corriger une **erreur bloquante** : commande non transmise, colis bloqué, clé API expirée, plafond atteint.

## 3. Créer les comptes et récupérer les clés

Prévoyez environ 2 heures. Notez chaque clé au fur et à mesure : vous les recopierez dans GitHub à l'étape 4.

### 3.1 Claude (le « cerveau » des agents) — obligatoire
1. Allez sur **console.anthropic.com** et créez un compte.
2. Ouvrez **Billing** et ajoutez un moyen de paiement. Fixez une limite mensuelle (par exemple 100 $).
3. Ouvrez **API Keys**, cliquez sur **Create Key** et copiez la clé → `ANTHROPIC_API_KEY`.

### 3.2 Shopify — obligatoire
1. Dans l'administration Shopify : **Paramètres → Applications et canaux de vente → Développer des applications → Créer une application**, nommée « PrecisVis Agents ».
2. Ouvrez **Configuration de l'API Admin** et cochez : `read_orders`, `read_products`, `write_products`, `read_inventory`, `read_files`, `write_files`, `read_customers`, `read_shopify_payments_disputes`.
3. Cliquez sur **Installer l'application**, puis révélez le **jeton d'accès Admin API** (il ne s'affiche qu'une fois) → `SHOPIFY_ADMIN_TOKEN`.
4. `SHOPIFY_SHOP` = l'adresse en `xxxx.myshopify.com`.

### 3.3 DSers — réglages dans l'application (pas de clé à fournir)
DSers n'a pas d'API publique. C'est l'application DSers qui passe les commandes ; le système vérifie qu'elle le fait bien.
- **Settings → Automatic Order** (commande automatique) : activé, avec un moyen de paiement AliExpress valide.
- **Settings → Tracking** : synchronisation du suivi vers Shopify activée, avec notification client.
- **Settings → Automatic Update** : mise à jour automatique du stock et des prix activée.

### 3.4 Meta (Page Facebook + Instagram) — publication organique
1. Vous devez avoir une **Page Facebook PrecisVis** et un **compte Instagram professionnel** relié à cette Page.
2. Sur **developers.facebook.com**, créez une application de type « Business ».
3. Ajoutez les produits **Facebook Login for Business** et **Instagram Graph API**.
4. Dans l'**Explorateur de l'API Graph**, générez un jeton avec : `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `read_insights`, `instagram_basic`, `instagram_content_publish`, `instagram_manage_insights`.
5. Transformez-le en **jeton de Page longue durée**. La méthode la plus simple est un « utilisateur système » dans le **Business Manager → Utilisateurs système** : son jeton n'expire pas → `META_PAGE_TOKEN`.
6. `META_PAGE_ID` : visible dans **Page → À propos → Transparence de la Page**.
7. `META_IG_USER_ID` : dans l'Explorateur, appelez `/{META_PAGE_ID}?fields=instagram_business_account`.
8. Veille concurrentielle (facultatif mais recommandé) : confirmez votre identité sur **facebook.com/ID**, puis acceptez les conditions de l'**API de la Bibliothèque publicitaire**. Sans cela, la veille se limite à la recherche web.

### 3.5 TikTok
1. Sur **developers.tiktok.com**, créez une application et ajoutez **Content Posting API** et **Login Kit**.
2. Scopes : `user.info.basic`, `video.publish`, `video.upload`, `video.list`.
3. Ajoutez l'adresse de votre boutique comme URL de redirection.
4. Récupérez `TIKTOK_CLIENT_KEY` et `TIKTOK_CLIENT_SECRET`.
5. Obtenez le premier jeton avec le petit script fourni :
   ```bash
   python scripts/tiktok_login.py
   ```
   Suivez les instructions affichées → `TIKTOK_REFRESH_TOKEN`.
6. **Important :** tant que TikTok n'a pas validé (« audité ») votre application, l'API ne publie qu'en **privé** (`SELF_ONLY`). Demandez l'audit depuis le portail TikTok. Une fois accepté, mettez `social.tiktok.privacy_level: PUBLIC_TO_EVERYONE` dans `config.yaml`.

### 3.6 Génération d'images et de vidéos
- **Sume** (fournisseur principal choisi) : Sume ne publie pas d'API REST. Le système passe par son **serveur MCP**. Demandez à Sume l'adresse du serveur MCP et un jeton d'accès utilisable depuis un serveur → `SUME_MCP_URL` et `SUME_MCP_TOKEN`. Sans ces deux valeurs, le système bascule automatiquement sur fal.ai.
- **fal.ai** (secours, recommandé) : créez un compte sur **fal.ai**, ajoutez du crédit (10 € suffisent pour commencer) et créez une clé dans **Dashboard → Keys** → `FAL_KEY`.
- **Déposez 3 à 8 vraies photos du produit** dans `brand/product_photos/`. Sans elles, la génération réelle est **bloquée** : c'est voulu, pour que les visuels montrent bien le produit livré.
- Remplacez `brand/logo.png` par votre vrai logo (PNG transparent).

### 3.7 E-mail du bilan (Resend)
1. Créez un compte sur **resend.com**, puis une clé dans **API Keys** → `RESEND_API_KEY`.
2. Pour commencer, l'expéditeur `onboarding@resend.dev` fonctionne, mais **uniquement vers l'adresse e-mail de votre compte Resend**. Créez donc votre compte Resend avec l'adresse qui doit recevoir le bilan (`reporting.to` dans `config.yaml`).
3. Ensuite, ajoutez et vérifiez votre domaine dans **Domains**, puis mettez `reporting.from: "PrecisVis <bilan@votre-domaine.fr>"`.

### 3.8 Boîte e-mail du SAV
Utilisez une adresse dédiée (par exemple `support@votre-domaine.fr` ou un Gmail dédié) :
1. Activez IMAP (Gmail : **Paramètres → Transfert et POP/IMAP**).
2. Activez la validation en 2 étapes, puis créez un **mot de passe d'application** (compte Google → Sécurité).
3. `SUPPORT_EMAIL` = l'adresse ; `SUPPORT_EMAIL_PASSWORD` = le mot de passe d'application.
4. Si ce n'est pas Gmail, changez `support.imap_host` et `support.smtp_host` dans `config.yaml`.

## 4. Déployer sur GitHub (recommandé)

Le dépôt contient déjà le planificateur : `.github/workflows/precisvis-daily.yml`.

1. Sur GitHub, ouvrez le dépôt, puis **Settings → Secrets and variables → Actions → New repository secret**.
2. Créez **un secret par ligne** du fichier `.env.example`, avec exactement le même nom (par exemple `ANTHROPIC_API_KEY`). Les secrets facultatifs peuvent rester absents.
3. Ouvrez l'onglet **Actions**. Si GitHub le demande, cliquez sur **I understand my workflows, go ahead and enable them**.
4. Le système tourne ensuite tout seul à 07:00, 12:30, 18:30 et 20:00 (heure de Paris, heure d'été comprise).

Bon à savoir :
- La base de données (journal, publications programmées, coûts du mois) est conservée entre deux exécutions grâce au cache GitHub.
- Les visuels de chaque exécution sont téléchargeables 14 jours : **Actions → une exécution → Artifacts**.
- Si la base est perdue (cache vidé après 7 jours sans exécution), le système repart de zéro sans danger. Le jeton TikTok renouvelé est alors repris depuis le secret : si TikTok le refuse, relancez `scripts/tiktok_login.py`.

## 5. Tester en simulation

En simulation (`--dry-run`), **rien n'est dépensé, rien n'est publié et aucun e-mail client ne part**. Les données sont fictives mais réalistes.

**Depuis GitHub :** **Actions → PrecisVis agents → Run workflow**, puis `phase = day` et `dry_run = coché`. Cochez aussi `send_test_email` pour recevoir le bilan de test par e-mail (il faut la clé Resend).

**Depuis un ordinateur** (Python 3.12 et ffmpeg installés) :
```bash
cd precisvis-agents
pip install -r requirements.txt
python main.py day --dry-run --fresh                    # journée complète simulée
python main.py day --dry-run --send-test-email          # idem + vrai e-mail bilan de test
python -m pytest -q                                     # tests automatiques
```
Le bilan simulé est enregistré dans `output/reports/AAAA-MM-JJ/` ; ouvrez le fichier `.html` dans votre navigateur.

## 6. Lire le bilan du soir

Objet : `PrecisVis — Bilan du JJ/MM : X ventes · Y € CA · ROAS n/a (organique) · Z vues`
(sans publicité payante, le ROAS n'a pas de sens : il est remplacé par les vues organiques).

1. **La journée en bref** : 3 lignes.
2. **Chiffres clés** : CA, commandes, panier moyen, marge estimée, coût de l'IA et vues, comparés à la veille et à la moyenne des 7 derniers jours.
3. **À traiter** : n'apparaît que s'il y a quelque chose à faire. **C'est la seule rubrique qui demande une action de votre part.**
4. **Ce que chaque agent a fait** : 2 à 5 puces par agent.
5. **Créas du jour** : miniatures et top 3 des publications.
6. **Publications organiques** : heure, réseau, statut et raison.
7. **Coûts du système** : IA texte, images et vidéos, comparés aux plafonds.
8. **Plan pour demain**.

La « marge estimée » vaut : prix de vente − coût produit − livraison − frais de paiement Shopify − publicité (0 €). Le coût du produit vient de Shopify s'il y est renseigné, sinon de `analytics.product_cost_eur`.

## 7. Arrêt d'urgence

**Tout arrêter tout de suite :**
1. Sur GitHub, ouvrez `precisvis-agents/config.yaml` et cliquez sur le crayon ✏️.
2. Remplacez `kill_switch: false` par `kill_switch: true`, puis cliquez sur **Commit changes**.

À la prochaine exécution, toutes les publications programmées sont annulées, les agents ne font plus rien et le bilan l'indique.

**Arrêt total, y compris des exécutions :** **Actions → PrecisVis agents → … → Disable workflow**.

**Reprendre :** remettez `kill_switch: false`, ou réactivez le workflow.

## 8. Régler le système (`config.yaml`)

| Réglage | Rôle | Valeur par défaut |
|---|---|---|
| `kill_switch` | Arrêt d'urgence | `false` |
| `budgets.api_daily_eur` / `api_monthly_eur` | Plafonds de coût IA | 5 € / 120 € |
| `paid_ads.*` | Publicité payante : **doit rester désactivée** | 0 € |
| `creatives.daily_images` / `daily_videos` | Volume de créas | 6 / 2 |
| `creatives.image_provider` / `video_provider` | `sume`, `fal` ou `placeholder` | `sume` (secours : `fal`) |
| `creatives.min_quality_score` | Note minimale d'un visuel | 7 |
| `social.*` | Nombre de posts par réseau et par jour | FB 2, IG 1 + 1 Reel, TikTok 2 |
| `schedule.publish_slots` | Heures de publication | 12:30, 18:30 |
| `catalog.banned_keywords` | Mots qui bloquent un produit (beauté) | liste fournie |
| `orders.alert_*` | Seuils d'alerte des commandes | 24 h / 5 j / 10 j |
| `support.auto_reply_categories` | Ce que le SAV peut traiter seul | suivi, délais, utilisation, infos retour |
| `analytics.*` | Coûts utilisés pour la marge | à ajuster à vos vrais coûts |
| `reporting.to` | Destinataire du bilan | votre adresse |

Le ton, le style et les consignes de chaque agent se modifient dans `prompts/*.md`. La charte graphique (couleurs, police, logo, style photo, caractéristiques autorisées du produit) se modifie dans `brand/brand.yaml`.

> ⚠️ Complétez `brand/brand.yaml → product_facts` avec la fiche du fournisseur. Les agents n'ont le droit de citer **que** ces caractéristiques.

Si vous modifiez les créneaux, adaptez aussi les lignes `cron` du fichier `.github/workflows/precisvis-daily.yml`.

## 9. Alternative : serveur VPS avec cron

Sur un petit serveur Linux (Ubuntu, environ 5 €/mois) :
```bash
sudo apt install -y python3.12 python3.12-venv ffmpeg git
git clone <votre dépôt> && cd <dépôt>/precisvis-agents
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env     # coller les clés
crontab -e
```
Puis ajoutez (le serveur doit être réglé sur l'heure de Paris : `sudo timedatectl set-timezone Europe/Paris`) :
```cron
0 7 * * *   cd ~/<dépôt>/precisvis-agents && .venv/bin/python main.py morning >> logs.txt 2>&1
30 12 * * * cd ~/<dépôt>/precisvis-agents && .venv/bin/python main.py publish >> logs.txt 2>&1
30 18 * * * cd ~/<dépôt>/precisvis-agents && .venv/bin/python main.py publish >> logs.txt 2>&1
0 20 * * *  cd ~/<dépôt>/precisvis-agents && .venv/bin/python main.py evening >> logs.txt 2>&1
```
Avantages : la base et les visuels restent sur le disque. Inconvénient : le serveur est à entretenir.

## 10. Conformité : à vérifier une fois

- [ ] **Mentions légales**, **CGV** (avec le formulaire de rétractation) et **politique de confidentialité** publiées sur Shopify (*Paramètres → Politiques*).
- [ ] Garantie légale de conformité de **2 ans** et droit de rétractation de **14 jours** : le système les ajoute aux fiches, ils doivent aussi figurer dans les CGV.
- [ ] **Marquage CE** et notice en français : demandez au fournisseur la déclaration de conformité **avant** de publier un produit (produit électrique avec batterie).
- [ ] Délai de livraison réaliste dans `catalog.shipping_delay_text` (actuellement « 7 à 12 jours ouvrés »).
- [ ] Contenu généré par IA : le système coche l'étiquette « contenu IA » sur TikTok et l'indique dans la légende. Sur Meta, activez l'étiquette IA si vous publiez des scènes très réalistes.
- [ ] Règles de publication Meta et TikTok : pas de faux avis, pas de marques tierces, pas d'avant/après trompeur. Ces règles sont déjà appliquées par les garde-fous.

## 11. Limites connues

- **DSers** : surveillance uniquement, car DSers n'a pas d'API publique. Le passage automatique des commandes se règle dans l'application DSers (section 3.3).
- **Sume** : utilisé via son serveur MCP, à condition d'obtenir une adresse et un jeton serveur. Sinon, c'est fal.ai qui génère.
- **TikTok** : publication en privé tant que l'audit n'est pas obtenu. Les posts photo TikTok sont désactivés (ils exigent un domaine vérifié chez TikTok).
- **TikTok Creative Center** : pas d'API publique. La veille TikTok passe par la recherche web de Claude.
- **Attribution des ventes** : elle repose sur les paramètres UTM. Les liens Facebook sont tracés publication par publication ; pour Instagram et TikTok (« lien en bio »), mettez dans la bio un lien avec `?utm_source=instagram` ou `?utm_source=tiktok`.
- Le SAV ne répond qu'aux e-mails. Les commentaires et messages privés des réseaux ne sont pas traités.

## 12. Pour les développeurs

```
precisvis-agents/
├── main.py                 # point d'entrée : morning | publish | evening | day  [--dry-run]
├── agents/                 # un fichier par agent + orchestrator.py
│   └── social_publisher.py # remplace « ads_manager » : publication organique, aucune campagne payante
├── core/                   # config, base SQLite, garde-fous, couche Claude Agent SDK, mise en page
├── tools/                  # Shopify, Meta, TikTok, images, vidéos, e-mail, DSers + doubles simulés (fakes.py)
├── prompts/                # prompt système de chaque agent
├── brand/                  # charte, polices, logo, vraies photos produit
├── templates/              # e-mail bilan (Jinja2)
├── output/creatives/       # AAAA-MM-JJ/<plateforme>/<format>/<id>.jpg|mp4 + .json
├── data/precisvis.db       # journal SQLite (tables actions, costs, agent_runs, creatives, posts, todo…)
└── tests/                  # pytest : garde-fous, mise en page, marge, DSers, orchestrateur, journée simulée
```

- Claude est appelé via `claude-agent-sdk` (`core/llm.py`) avec une sortie JSON structurée. Les outils intégrés sont restreints agent par agent : `Read` pour la vision, `WebSearch`/`WebFetch` pour la veille, MCP Sume pour la génération. Le budget restant est transmis en `max_budget_usd`.
- L'IA génère la scène **sans texte**. Le titre et le logo sont posés par `core/compose.py`, ce qui garantit à 100 % le respect des zones de sécurité 9:16 et de la limite de 7 mots.
- Les chiffres (CA, marge, alertes de commandes, classement des créas) sont calculés en Python, sans IA.
