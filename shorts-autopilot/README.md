# Shorts Autopilot

Pipeline autonome et 100 % gratuit qui fabrique et publie 2 à 4 vidéos courtes par jour
(YouTube Shorts, Instagram Reels, TikTok) : veille → script vérifié → voix off → B-roll →
sous-titres mot par mot → montage → contrôle qualité → publication par API officielle →
statistiques → apprentissage.

Aucun outil payant, aucun GPU, aucune automatisation de navigateur, aucun faux engagement.

---

## 0. À lire d'abord : ce qui est réaliste et ce qui ne l'est pas

| Votre demande | Réalité (règles vérifiées en novembre 2026) | Ce que fait le projet |
|---|---|---|
| 100 % autonome **et** monétisé sur YouTube | La politique « contenu non authentique » de YouTube exclut de la monétisation le contenu produit en masse, répétitif, sans apport humain. La presse rapporte un durcissement en juillet 2026 (vidéos IA répétitives, personas synthétiques sur la finance et la santé). Plusieurs templates ne suffisent **pas** à s'en protéger. | Scripts ancrés sur une source et vérifiés, angle éditorial propre à votre chaîne, formats/hooks/montages qui tournent, et un mode **veto** par Telegram (vous voyez chaque vidéo avant publication). Aucune garantie de monétisation n'est possible. |
| Publication automatique sur TikTok | Une app non auditée ne peut publier qu'en **privé**. L'audit TikTok vise des produits destinés à des utilisateurs tiers ; un outil à usage personnel a de fortes chances d'être refusé. | Mode `inbox` : la vidéo arrive en brouillon dans votre app TikTok, vous appuyez sur « Publier ». Mode `direct` prêt si vous obtenez l'audit. |
| Publication automatique sur YouTube | Possible, mais un projet Google Cloud créé après le 28/07/2020 voit ses envois API **verrouillés en privé** tant qu'il n'a pas passé l'audit de conformité de l'API YouTube (formulaire gratuit). | Le code détecte ce verrouillage et vous prévient sur Telegram. Procédure d'audit au §6. |
| Publication automatique de Reels | Possible sans validation d'app pour **votre propre** compte professionnel. | Envoi résumable, pas besoin d'héberger la vidéo. |
| Revenus rapides | Le RPM des Shorts est très bas : environ 0,10–0,30 $ pour 1 000 vues (audience US), 0,04–0,10 $ en France. Monétisation Shorts : 1 000 abonnés + 10 M de vues Shorts sur 90 jours. | 3 vidéos/jour à 2 000 vues ≈ 180 000 vues/mois ≈ 20–50 $/mois une fois monétisé. Le vrai levier est ailleurs (affiliation, vidéos longues, produit). |
| Stats de rétention partout | YouTube Analytics les fournit (avec ~2 jours de délai), Instagram donne le temps de visionnage moyen, **TikTok ne fournit pas la rétention** par API. | L'apprentissage utilise ce qui existe et se renormalise par plateforme. |
| Musique automatique | Il n'existe pas d'API gratuite fiable de musique libre de droits. | Vous déposez une fois quelques morceaux dans `assets/music/`, ils tournent ensuite tout seuls. |

Les chiffres de RPM viennent de blogs spécialisés qui se contredisent : ce sont des ordres de grandeur.
Les pages officielles Google/TikTok/Meta n'étaient pas consultables directement depuis l'environnement
où ce projet a été construit ; les règles ci-dessus viennent de résultats de recherche citant ces pages.
**Revérifiez les trois points marqués §6, §7, §8 dans vos consoles développeur avant de passer en live.**

---

## 1. Choix de la niche

| | RPM Shorts estimé | Concurrence | Faceless | Viralité | Risque démonétisation |
|---|---|---|---|---|---|
| **1. Tech & IA utile (EN, US)** — `tech_ai_en` | 0,09–0,30 $ | forte | très facile (actu quotidienne, B-roll abondant) | élevée | faible |
| **2. Business expliqué (EN, US)** — `business_en` | 0,10–0,25 $ | moyenne | facile | moyenne | faible à moyen |
| **3. Finances perso, éducation (EN, US)** — `finance_en` | 0,15–0,45 $ | très forte | facile | moyenne | **élevé** (sujet sensible, ciblé par YouTube en 2026) |

**Français ou anglais ?** L'audience US rapporte environ 2 à 3 fois plus par vue (0,10–0,32 $ contre
0,04–0,10 $) et le marché est bien plus grand, mais la concurrence aussi. Deux nuances :
TikTok diffuse surtout dans la région du compte (un compte créé en France touchera mal les États-Unis),
et le programme de récompenses TikTok exige des vidéos de plus d'une minute.

**Recommandation : `tech_ai_en`** (défaut). Meilleur compromis revenu / risque, et chaque vidéo s'appuie
sur un article daté, ce qui la rend vérifiable. La variante française `tech_ia_fr` est fournie : même
pipeline, changez `NICHE` dans `.env`. La finance n'est à envisager qu'avec validation humaine
obligatoire (déjà imposée dans `finance_en.yaml`).

Changer de niche = changer une ligne. Créer la vôtre = copier un fichier de `config/niches/`.

---

## 2. Démarrage en mode test (15 minutes, rien n'est publié)

Prérequis : Docker et Docker Compose. 4 Go de RAM libres, ~3 Go de disque.

```bash
cd shorts-autopilot
cp .env.example .env          # puis remplissez les clés du §3
docker compose build
docker compose run --rm autopilot python -m autopilot doctor         # vérifie tout
docker compose run --rm autopilot python -m autopilot generate --demo   # 1 vidéo sans aucune clé
docker compose run --rm autopilot python -m autopilot generate -n 10    # vos 10 vidéos à valider
```

Les vidéos arrivent dans `output/review/<id>/video.mp4`, avec un `meta.json` (script, source, légendes
par plateforme, rapport de contrôle qualité). Regardez-les **avec le son** avant d'aller plus loin.
Au premier lancement, les modèles de voix (~120 Mo) et Whisper (~150 Mo) se téléchargent une fois.

Comptez 1 à 3 minutes de calcul par vidéo sur 4 cœurs.

---

## 3. Clés gratuites (aucune carte bancaire)

| Variable `.env` | Où l'obtenir |
|---|---|
| `GEMINI_API_KEY` | <https://aistudio.google.com/apikey>. Le palier gratuit a été fortement réduit en 2026 et varie par modèle : vos limites réelles s'affichent dans AI Studio. Besoin : ~3 appels par vidéo. |
| `PEXELS_API_KEY` | <https://www.pexels.com/api/> (réponse immédiate) |
| `PIXABAY_API_KEY` | <https://pixabay.com/api/docs/> (visible une fois connecté) |
| `TELEGRAM_BOT_TOKEN` | Dans Telegram, parlez à **@BotFather** → `/newbot`. Puis envoyez `/start` à votre nouveau bot. |
| `TELEGRAM_CHAT_ID` | Parlez à **@userinfobot**, il vous donne votre identifiant numérique. |

**Sans clé Gemini ou si le quota est épuisé** : LLM local Ollama, illimité.

```bash
docker compose --profile ollama up -d
docker compose exec ollama ollama pull qwen2.5:7b
# dans .env :  OLLAMA_HOST=http://ollama:11434
```

**Musique** : déposez 5 à 10 morceaux libres de droits (mp3/wav) dans `assets/music/`
(Bibliothèque audio YouTube, Pixabay Music). Conservez la preuve de licence de chaque morceau.

---

## 4. Ce que fait chaque étape

1. **Veille** (`topics.py`) : flux RSS de la niche, RSS Reddit, tendances Google Trends. Filtre hors-niche,
   mots-clés à risque, et doublons sur 45 jours.
2. **Script** (`script.py`) : hook de moins de 2 secondes, structure rétention, appel à l'action. Six
   formats et six styles de hook tournent. Trois garde-fous : tout chiffre prononcé doit figurer dans
   la source ; formulations interdites (promesses, conseils personnalisés) ; seconde passe LLM de
   fact-checking. Un script qui échoue trois fois est abandonné, jamais publié.
3. **Voix** (`tts.py`) : Kokoro (défaut) ou Piper, en local.
4. **Sous-titres** (`align.py`, `subtitles.py`) : Whisper donne le timing mot par mot, recalé sur le texte
   exact du script ; le mot prononcé s'allume, les mots-clés sont en couleur.
5. **B-roll** (`broll.py`) : Pexels/Pixabay d'après la requête visuelle de chaque phrase, sans réutiliser
   un clip avant 30 jours.
6. **Montage** (`render.py`, `templates.py`) : 1080x1920, 30 i/s, coupes rapides, zooms et panoramiques,
   musique basse avec atténuation automatique sous la voix. Quatre templates réellement différents.
7. **Contrôle qualité** (`qc.py`) : durée 30–75 s, format, niveau audio, silences, sous-titres complets
   et synchronisés (taux de mots reconnus par Whisper ≥ 80 %).
8. **Publication** (`publisher.py`) : à l'heure du créneau, avec étiquette IA native sur chaque plateforme.
9. **Apprentissage** (`learn.py`) : chaque nuit, les stats deviennent un score par vidéo ; un bandit
   favorise les catégories, formats, hooks, templates et créneaux qui marchent, en gardant 20 % d'exploration.

---

## 5. Passer en production

Une fois vos 10 vidéos validées et au moins une plateforme connectée (§6 à §8) :

```bash
# dans .env :  MODE=live
docker compose up -d            # tourne en continu, redémarre tout seul
docker compose logs -f autopilot
```

Vous recevez sur Telegram : chaque vidéo fabriquée (avec boutons **Publier / Rejeter**), chaque
publication avec son lien, chaque erreur, et un bilan quotidien.

Mode de validation (`approval.mode` dans `config/config.yaml`) :

- `veto` (défaut, recommandé) : publiée à l'heure prévue sauf si vous cliquez « Rejeter ».
- `required` : rien ne part sans votre clic « Publier ».
- `off` : aucune intervention.

Commandes utiles :

```bash
docker compose exec autopilot python -m autopilot doctor
docker compose exec autopilot python -m autopilot stats       # collecte + apprentissage maintenant
docker compose exec autopilot python -m autopilot report      # bilan maintenant
docker compose exec autopilot python -m autopilot publish <id> -p youtube   # republier à la main
```

---

## 6. YouTube : app, OAuth, audit

1. <https://console.cloud.google.com> → créez un projet.
2. **API et services → Bibliothèque** : activez **YouTube Data API v3** et **YouTube Analytics API**.
3. **Écran de consentement OAuth** : type *Externe*, nom de l'app, votre e-mail. Puis
   **Publier l'application** (état « En production »). En état « Test », le jeton expire tous les 7 jours.
4. **Identifiants → Créer → ID client OAuth → Application de bureau**. Copiez l'ID et le secret dans `.env`.
5. Connexion :
   ```bash
   docker compose run --rm autopilot python -m autopilot auth youtube
   ```
   Ouvrez le lien, choisissez la chaîne, acceptez (écran « application non validée » → *Paramètres avancés*
   → *Continuer*). Le navigateur arrive sur une page `localhost` en erreur : copiez son adresse complète
   et collez-la dans le terminal.
6. **Audit de conformité (obligatoire pour des vidéos publiques)** : remplissez le formulaire
   « YouTube API Services – Audit and Quota Extension Form » depuis l'aide développeur YouTube. Décrivez
   honnêtement l'usage : envoi de vos propres vidéos sur votre propre chaîne, déclaration du contenu
   synthétique activée. Tant que l'audit n'est pas passé, chaque envoi est verrouillé en privé et
   Telegram vous le signale. En attendant, publiez à la main les fichiers de `output/`.

**Quotas** : 10 000 unités/jour par défaut. Le coût d'un envoi était de 1 600 unités ; plusieurs sources
indiquent une baisse à ~100 fin 2025. Dans les deux cas, 4 envois par jour passent. Vérifiez dans
*API et services → Quotas*.

**Étiquetage IA** : le champ `status.containsSyntheticMedia` est envoyé à `true`.

---

## 7. TikTok : app, OAuth, audit

1. <https://developers.tiktok.com> → *Manage apps* → créez une app. Il faut une icône, une description,
   l'adresse de votre site, une page de conditions d'utilisation et une page de confidentialité.
2. Ajoutez les produits **Login Kit** et **Content Posting API** (activez *Direct Post* si vous visez le
   mode `direct`). Scopes : `user.info.basic`, `video.upload`, `video.publish`, `video.list`.
3. Déclarez une URI de redirection en HTTPS sur un domaine à vous (par exemple
   `https://votre-domaine/tiktok-callback` ; la page n'a pas besoin d'exister). Mettez la même dans
   `TIKTOK_REDIRECT_URI`, avec `TIKTOK_CLIENT_KEY` et `TIKTOK_CLIENT_SECRET`.
4. En mode *Sandbox*, ajoutez votre compte TikTok comme utilisateur de test, puis :
   ```bash
   docker compose run --rm autopilot python -m autopilot auth tiktok
   ```
5. Dans `config/config.yaml` : `platforms.tiktok.enabled: true`.

**L'audit, honnêtement.** Sans audit, le mode `direct` ne publie qu'en privé (`SELF_ONLY`), sur un compte
lui-même privé. L'audit vérifie l'usage prévu et une interface de publication précise (nom du créateur
affiché, choix de visibilité par l'utilisateur, réglages commentaires/duos, consentement). Un script sans
interface pour un seul compte ne correspond pas à ce que TikTok approuve. Vos options réalistes :

- **`mode: inbox`** (défaut) : la vidéo arrive en brouillon, vous publiez en un geste. À confirmer dans
  votre console : ce mode demande la validation du scope `video.upload` mais pas l'audit Direct Post.
- Programmer vous-même les fichiers de `output/` dans **TikTok Studio** (gratuit, officiel).
- Tenter l'audit si vous transformez l'outil en vrai produit avec interface et plusieurs utilisateurs.

**Étiquetage IA** : `is_aigc: true` en mode direct. En mode inbox, activez « Contenu généré par IA »
au moment de publier dans l'app.

---

## 8. Instagram : app et jeton

1. Passez votre compte Instagram en **compte professionnel** (Créateur ou Entreprise).
2. <https://developers.facebook.com> → *Créer une app* → cas d'usage Instagram → **API setup with
   Instagram login**.
3. *Rôles de l'app* → ajoutez votre compte comme **testeur Instagram**, puis acceptez l'invitation dans
   Instagram (*Paramètres → Applications et sites web → Invitations de testeur*).
4. Dans la configuration de l'API, **Generate token** à côté de votre compte. Permissions :
   `instagram_business_basic`, `instagram_business_content_publish`,
   `instagram_business_manage_insights`.
5. Collez le jeton dans `INSTAGRAM_ACCESS_TOKEN`, puis :
   ```bash
   docker compose run --rm autopilot python -m autopilot auth instagram
   ```
   Le jeton dure 60 jours ; il est prolongé automatiquement chaque semaine.

Pour votre propre compte en rôle testeur, aucune validation d'app n'est nécessaire.
**Limite** : 50 à 100 publications par 24 h selon les pages de Meta, très au-dessus du besoin.
**Étiquetage IA** : paramètre `is_ai_generated` (ajouté par Meta en juin 2026). Si votre version d'API
le refuse, la vidéo part quand même avec la mention en légende et Telegram vous prévient : montez alors
`platforms.instagram.api_version`.

---

## 9. Serveur gratuit Oracle Cloud (Always Free)

1. Créez une instance **VM.Standard.A1.Flex** (ARM, 4 OCPU, 24 Go), image Ubuntu 24.04.
   Si « Out of host capacity », réessayez plus tard ou changez de domaine de disponibilité.
2. ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
   sudo usermod -aG docker $USER && newgrp docker
   git clone <votre dépôt> && cd <dépôt>/shorts-autopilot
   cp .env.example .env && nano .env
   docker compose up -d --build
   ```
3. Les connexions OAuth (§6 à §8) se font en collant une adresse dans le terminal : pas besoin de
   navigateur sur le serveur.

Oracle peut récupérer les instances gratuites restées inactives ; passer le compte en « Pay As You Go »
(sans rien dépenser dans les limites Always Free) est réputé l'éviter. À vérifier chez Oracle.

Sans Docker (PC) : `pip install -r requirements.txt`, installez FFmpeg, puis `python -m autopilot run`.
Pour un cron classique à la place du planificateur intégré : `python -m autopilot generate` aux heures voulues.

---

## 10. Réglages

Tout est commenté dans `config/config.yaml` (général) et `config/niches/*.yaml` (ligne éditoriale,
flux, créneaux, voix, mots interdits). Les plus utiles :

- `schedule.posts_per_day` : 2 à 4.
- `niche.angle` : **personnalisez-le**. C'est votre voix éditoriale, donc votre meilleure protection
  contre le classement « contenu répétitif ».
- `script.min_words` / `max_words` : durée des vidéos (165+ mots pour dépasser 60 s).
- `render.templates` : retirez un template que vous n'aimez pas, ou ajoutez le vôtre dans `templates.py`.
- `learning.explore_rate` : part de hasard conservée.

Données : tout l'état est dans `data/` (base SQLite, jetons, logs dans `data/logs/autopilot.log`).
Sauvegardez ce dossier. Il n'est jamais versionné, pas plus que `.env`.

## 11. Tests

```bash
pip install pytest && python -m pytest tests
```

## 12. Dépannage

| Symptôme | Cause probable |
|---|---|
| « Aucun LLM disponible » | Quota Gemini du jour épuisé ou clé absente → activez Ollama (§3). |
| Vidéos sur fond dégradé | Clé Pexels/Pixabay absente ou requêtes sans résultat. |
| YouTube publie en privé | Audit de l'API non passé (§6). |
| `invalid_grant` YouTube après 7 jours | Écran de consentement resté en « Test » (§6, étape 3). |
| TikTok `unaudited_client_can_only_post_to_private_accounts` | App non auditée (§7) : utilisez `mode: inbox`. |
| QC « voix ≠ sous-titres » | Synthèse vocale ratée sur ce texte ; la vidéo est écartée, c'est voulu. |
| Un flux RSS en ❌ dans `doctor` | Le site a changé son flux : remplacez-le dans le fichier de niche. |
