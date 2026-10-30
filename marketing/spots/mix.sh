#!/usr/bin/env bash
# Final mix of the QomiR radio and TV spots.
# Expects in the current directory: client.mp3, vo_radio.mp3, vo_tv.mp3 (voice-overs),
# audio/{music_radio,music_tv,amb,ding,tap,whoosh}.wav (from synth_audio.py), tv_video_muet.mp4.
# Writes out/radio_web.mp3 (-16 LUFS), out/radio_broadcast.wav (-23 LUFS, EBU R128),
# out/tv_web.mp4 (-16 LUFS) and out/tv_broadcast.mp4 (-23 LUFS).
set -euo pipefail
mkdir -p work out

dur() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1"; }

# ---- voices: cap long pauses, light EQ/compression ----
VOICE_FX="highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,equalizer=f=3500:t=q:w=1:g=2"
ffmpeg -loglevel error -y -i client.mp3 -af "silenceremove=stop_periods=-1:stop_duration=0.3:stop_threshold=-45dB:stop_silence=0.22,$VOICE_FX,aresample=44100" -ac 2 work/client.wav
ffmpeg -loglevel error -y -i vo_radio.mp3 -af "silenceremove=stop_periods=-1:stop_duration=0.45:stop_threshold=-45dB:stop_silence=0.35,atempo=1.04,$VOICE_FX,aresample=44100" -ac 2 work/vo_radio.wav
ffmpeg -loglevel error -y -i vo_tv.mp3 -af "$VOICE_FX,aresample=44100" -ac 2 work/vo_tv.wav

# word timings of the processed radio VO, to place the sound effects
read -r T_TAP T_DING < <(python3 - <<'EOF'
from faster_whisper import WhisperModel
m = WhisperModel("small", compute_type="int8")
segs, _ = m.transcribe("work/vo_radio.wav", language="fr", word_timestamps=True)
words = [w for s in segs for w in s.words]
tap = next((w.end for w in words if "application" in w.word.lower()), 9.0)
ding = next((w.start for w in words if w.word.strip().lower().startswith("arrive")), 10.0)
print(f"{tap:.2f} {ding:.2f}")
EOF
)

# ---- radio ----
C_END=$(dur work/client.wav)
VO_AT=$(python3 -c "print(round(0.35 + $C_END + 0.15, 2))")
MUSIC_AT=$(python3 -c "print(round($VO_AT - 0.9, 2))")
ms() { python3 -c "print(int(round(($1)*1000)))"; }
ffmpeg -loglevel error -y \
  -i audio/amb.wav -i work/client.wav -i work/vo_radio.wav -i audio/music_radio.wav -i audio/tap.wav -i audio/ding.wav \
  -filter_complex "
    [0]volume=0.55,afade=t=out:st=$(python3 -c "print($VO_AT-0.6)"):d=1.4[amb];
    [1]adelay=350|350,volume=1.0[cli];
    [2]adelay=$(ms $VO_AT)|$(ms $VO_AT)[vo];
    [vo]asplit=2[vo1][vosc];
    [3]adelay=$(ms $MUSIC_AT)|$(ms $MUSIC_AT),volume=0.9[mus];
    [mus][vosc]sidechaincompress=threshold=0.02:ratio=9:attack=30:release=500:makeup=1[musd];
    [4]adelay=$(ms "$VO_AT+$T_TAP")|$(ms "$VO_AT+$T_TAP"),volume=0.35[tap];
    [5]adelay=$(ms "$VO_AT+$T_DING-0.15")|$(ms "$VO_AT+$T_DING-0.15"),volume=0.28[ding];
    [amb][cli][vo1][musd][tap][ding]amix=inputs=6:normalize=0:duration=longest,atrim=0:31,afade=t=out:st=30.2:d=0.8[mix]" \
  -map "[mix]" -c:a pcm_s24le work/radio_mix.wav

ffmpeg -loglevel error -y -i work/radio_mix.wav -af loudnorm=I=-16:TP=-1.0:LRA=9 -ar 44100 -c:a libmp3lame -b:a 256k out/radio_web.mp3
ffmpeg -loglevel error -y -i work/radio_mix.wav -af loudnorm=I=-23:TP=-1.0:LRA=9 -ar 48000 -c:a pcm_s24le out/radio_broadcast.wav

# ---- TV (VO starts at 2.0 s, cuts as in tv.html) ----
if [ -f tv_video_muet.mp4 ]; then
ffmpeg -loglevel error -y \
  -i work/vo_tv.wav -i audio/music_tv.wav -i audio/amb.wav -i audio/whoosh.wav -i audio/tap.wav -i audio/ding.wav \
  -filter_complex "
    [0]adelay=2000|2000[vo];
    [vo]asplit=2[vo1][vosc];
    [1]volume=0.9[mus];
    [mus][vosc]sidechaincompress=threshold=0.02:ratio=9:attack=30:release=500:makeup=1[musd];
    [2]volume=0.35,afade=t=out:st=2.2:d=1.2[amb];
    [3]asplit=4[w1][w2][w3][w4];
    [w1]adelay=3050|3050,volume=0.22[a1];[w2]adelay=7700|7700,volume=0.22[a2];
    [w3]adelay=13450|13450,volume=0.22[a3];[w4]adelay=17950|17950,volume=0.22[a4];
    [4]adelay=9350|9350,volume=0.35[tap];
    [5]adelay=11500|11500,volume=0.26[ding];
    [vo1][musd][amb][a1][a2][a3][a4][tap][ding]amix=inputs=9:normalize=0:duration=longest,atrim=0:30,afade=t=out:st=29.3:d=0.7[mix]" \
  -map "[mix]" -c:a pcm_s24le work/tv_mix.wav

ffmpeg -loglevel error -y -i tv_video_muet.mp4 -i work/tv_mix.wav -map 0:v -map 1:a -c:v copy \
  -af loudnorm=I=-16:TP=-1.0:LRA=9 -ar 48000 -c:a aac -b:a 256k -shortest -movflags +faststart out/tv_web.mp4
ffmpeg -loglevel error -y -i tv_video_muet.mp4 -i work/tv_mix.wav -map 0:v -map 1:a -c:v copy \
  -af loudnorm=I=-23:TP=-1.0:LRA=9 -ar 48000 -c:a aac -b:a 320k -shortest -movflags +faststart out/tv_broadcast.mp4

fi

for f in out/*; do echo "$f $(dur "$f")"; done
echo "radio: vo_at=$VO_AT tap=$T_TAP ding=$T_DING"
