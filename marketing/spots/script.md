# QomiR App — spots radio & TV

Voix off : ElevenLabs (via Higgsfield), français, voix masculine « Andre ».
« QomiR » est écrit « Komir » dans le texte envoyé à la synthèse vocale pour être prononcé correctement.

---

## Spot radio — 30 s

| Temps | Son | Texte |
|---|---|---|
| 0:00 | Ambiance restaurant (brouhaha, verres) | |
| 0:00 | CLIENTE (agacée) | « Excusez-moi ? … S'il vous plaît ! … On peut commander ? » |
| 0:04 | Musique bistrot (guitare, piano) démarre, l'ambiance s'efface | |
| 0:04 | VOIX OFF | « Restaurateurs, vos clients attendent pour commander ? Avec QomiR App, ils scannent le QR code sur leur table, et commandent directement depuis leur téléphone. Sans application. » |
| | Clic tactile | |
| | VOIX OFF + « ding » de cuisine | « La commande arrive aussitôt en cuisine ou au bar. » |
| | VOIX OFF | « Moins d'attente, zéro erreur, et plus de clients servis, avec la même équipe. Menu modifiable en un clic, multi-langues, statistiques en temps réel. » |
| fin | VOIX OFF, musique qui conclut | « QomiR App. Scannez, commandez, c'est servi. Demandez votre démo sur qomirapp.com. » |

---

## Spot TV — 30 s, 16:9 (1920×1080)

| Temps | Image | Incrustation | Voix off |
|---|---|---|---|
| 0:00 | Le client pousse la porte | Ce soir — Chez vous. | (musique) |
| 0:03 | La salle du bistrot | Fini l'attente — Plus personne n'attend. | « Ce soir, dans votre restaurant, plus personne n'attend. » |
| 0:05 | Il s'assoit, QR code sur la table | Sur chaque table — Un QR code. | « Un QR code sur la table. » |
| 0:07 | Scan par-dessus l'épaule (cadre de scan animé) | Sans application — Ils scannent. | « Vos clients scannent, |
| 0:08 | Il fait défiler (carte menu animée) | Menu digital — Découvrent le menu. | découvrent le menu, |
| 0:09 | Pouce sur l'écran (toast « Commande envoyée ») | En 1 clic — Et commandent. | et commandent. Sans application. » |
| 0:11 | Le chef lit l'écran (ticket « Table 12 ») | En temps réel — Reçue en cuisine. | « La commande arrive aussitôt en cuisine. » |
| 0:13 | Pâte et four à pizza | Gain de temps — L'équipe se concentre sur la qualité. | « Votre équipe se concentre sur la qualité. » |
| 0:16 | La cuisinière dresse | Zéro erreur — Moins d'erreurs. | « Moins d'erreurs, |
| 0:17 | Passe-plat | Service ultra-rapide — Plus rapide. | un service plus rapide, |
| 0:18 | La pizza est servie | Augmentez votre CA — Plus de clients servis. | et plus de clients servis. » |
| 0:20 | Client souriant + chiffres 30s / 0 app / 100 % | QomiR App — Fluidifiez votre restaurant. | « QomiR App. Fluidifiez votre restaurant. » |
| 0:23 | Carte de fin : logo, « Scannez, commandez, c'est servi. », 7 services, bouton, qomirapp.com | | « Demandez votre démo sur qomirapp.com. » |

Services cités sur la carte de fin : commande par QR code, sans application, menu modifiable, multi-langues, allergènes, statistiques en temps réel, paiement intégré.

---

## Fichiers

- `tv.html` : animation du spot TV (rendu image par image avec `render.js`, `VW=1920 VH=1080`)
- `tv_video_muet.mp4` : image du spot TV sans le son
- `synth_audio.py` → `audio/` : musique et bruitages (générés, sans échantillon externe)
- `mix.sh` : mixage final (voix + musique + bruitages, normalisation), lancé dans le bac à sable Higgsfield

## Versions finales (mixées, bibliothèque Higgsfield)

| Fichier | Usage | Lien |
|---|---|---|
| Spot radio, web/réseaux (−16 LUFS, MP3) | écoute, réseaux sociaux | https://d2ol7oe51mr4n9.cloudfront.net/user_3LL6DgBBOWkStQrbtoxyyrV5WOT/01bab40b-c957-48c2-9b01-711120e0f575.mp3 |
| Spot radio, diffusion (−23 LUFS EBU R128, MP3 320k) | régie radio | https://d2ol7oe51mr4n9.cloudfront.net/user_3LL6DgBBOWkStQrbtoxyyrV5WOT/8f2c52ea-2d70-44d3-bd6c-e4373dc3a1ec.mp3 |
| Spot TV, web/réseaux (−16 LUFS) | YouTube, réseaux, site | https://d2ol7oe51mr4n9.cloudfront.net/user_3LL6DgBBOWkStQrbtoxyyrV5WOT/bbfeb1ee-888b-4064-acb9-a458274f0318.mp4 |
| Spot TV, diffusion (−23 LUFS EBU R128) | régie TV | https://d2ol7oe51mr4n9.cloudfront.net/user_3LL6DgBBOWkStQrbtoxyyrV5WOT/96ecc23b-1666-4f8f-979d-77a71fa165aa.mp4 |
