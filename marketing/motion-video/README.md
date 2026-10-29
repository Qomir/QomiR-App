# Vidéo motion design QomiR (9:16)

- `QomiR_motion_9x16.mp4` : 1080×1920, 30 fps, 17,5 s, avec musique synthétisée
- `QomiR_motion_9x16_sans_son.mp4` : même vidéo, sans piste audio

## Régénérer

```bash
npm i three@0.169.0          # dans ce dossier
npx http-server -p 8765 -s . &
mkdir frames && node render.js http://127.0.0.1:8765/index.html frames full
ffmpeg -framerate 30 -i frames/f%04d.png -c:v libx264 -crf 17 -pix_fmt yuv420p out.mp4
```

`index.html` contient la scène Three.js et la timeline ; `window.setTime(t)` rend l'image à l'instant `t`.
Prévisualiser une image : `index.html?t=8.5`.
