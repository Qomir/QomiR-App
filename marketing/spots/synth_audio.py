"""Synthesise the music bed and sound effects for the QomiR radio/TV spots.

Usage: python3 synth_audio.py OUT_DIR [RADIO_MUSIC_SECONDS]
Writes music_radio.wav, music_tv.wav, amb.wav, ding.wav, tap.wav, whoosh.wav (44.1 kHz).
Deterministic (fixed seed), no external samples.
"""
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
rng = np.random.default_rng(7)


def write(path, x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    peak = np.max(np.abs(x)) or 1.0
    x = x / peak * 0.89
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def onepole_lp(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def pluck(freq, dur, bright=0.5):
    """Karplus-Strong plucked string (nylon guitar-ish)."""
    n = int(dur * SR)
    period = int(SR / freq)
    buf = rng.uniform(-1, 1, period)
    buf = onepole_lp(buf, 2000 + 5000 * bright)
    out = np.empty(n)
    decay = 0.996
    for i in range(n):
        j = i % period
        out[i] = buf[j]
        buf[j] = decay * 0.5 * (buf[j] + buf[(j + 1) % period])
    return out


def epiano(freq, dur):
    t = np.arange(int(dur * SR)) / SR
    env = np.exp(-t * 2.2) * (1 - np.exp(-t * 300))
    tone = np.sin(2 * np.pi * freq * t + 0.6 * np.exp(-t * 4) * np.sin(2 * np.pi * freq * 2 * t))
    tone += 0.25 * np.sin(2 * np.pi * freq * 3 * t) * np.exp(-t * 5)
    return tone * env


def bass(freq, dur):
    t = np.arange(int(dur * SR)) / SR
    env = np.minimum(1, t * 80) * np.exp(-t * 1.6)
    return (np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(4 * np.pi * freq * t)) * env


def kick(dur=0.4):
    t = np.arange(int(dur * SR)) / SR
    f = 48 + 90 * np.exp(-t * 35)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def snap(dur=0.18):
    t = np.arange(int(dur * SR)) / SR
    n = rng.uniform(-1, 1, t.size)
    n = n - onepole_lp(n, 1200)
    return n * np.exp(-t * 28)


def shaker(dur=0.07):
    t = np.arange(int(dur * SR)) / SR
    n = rng.uniform(-1, 1, t.size)
    n = n - onepole_lp(n, 6000)
    return n * np.exp(-t * 60) * np.minimum(1, t * 400)


def add(buf, x, at, gain=1.0):
    i = int(at * SR)
    if i >= buf.size:
        return
    end = min(buf.size, i + x.size)
    buf[i:end] += gain * x[: end - i]


# C - G - Am - F, one bar each
CHORDS = [
    (48, [60, 64, 67, 72]),
    (43, [59, 62, 67, 71]),
    (45, [57, 60, 64, 69]),
    (41, [57, 60, 65, 69]),
]


def music(total, bpm=112, intro_beats=4, out_fade=1.6):
    beat = 60 / bpm
    bar = 4 * beat
    L = np.zeros(int((total + 3) * SR))
    R = np.zeros_like(L)
    nbars = int(np.ceil(total / bar)) + 1
    pluck_cache, piano_cache = {}, {}
    for b in range(nbars):
        t0 = b * bar
        if t0 >= total:
            break
        root, tones = CHORDS[b % 4]
        last = t0 + bar >= total - 0.01
        # piano chord on the bar, panned slightly left
        for k, m in enumerate(tones[:3]):
            p = piano_cache.setdefault(m, epiano(hz(m), bar * 1.2))
            add(L, p, t0 + k * 0.012, 0.16)
            add(R, p, t0 + k * 0.012, 0.10)
        # guitar arpeggio in eighths, panned right
        pattern = [0, 1, 2, 3, 2, 1, 2, 3]
        for e, idx in enumerate(pattern):
            m = tones[idx]
            s = pluck_cache.setdefault(m, pluck(hz(m), 1.2))
            add(L, s, t0 + e * beat / 2, 0.16)
            add(R, s, t0 + e * beat / 2, 0.26)
        # bass on 1 and 3 (and a pickup on the and-of-4)
        bs = bass(hz(root), beat * 1.8)
        add(L, bs, t0, 0.42); add(R, bs, t0, 0.42)
        add(L, bs, t0 + 2 * beat, 0.34); add(R, bs, t0 + 2 * beat, 0.34)
        if b * 4 >= intro_beats:
            for q in range(4):
                tq = t0 + q * beat
                if q in (0, 2):
                    add(L, kick(), tq, 0.55); add(R, kick(), tq, 0.55)
                else:
                    add(L, snap(), tq, 0.11); add(R, snap(), tq, 0.13)
                for s16 in range(4):
                    g = 0.025 if s16 % 2 else 0.018
                    add(L, shaker(), tq + s16 * beat / 4, g * 0.6)
                    add(R, shaker(), tq + s16 * beat / 4, g)
    # final ringing C chord
    end_at = total - 2.2
    for m in [48, 60, 64, 67, 72]:
        add(L, epiano(hz(m), 3.0), end_at, 0.14); add(R, epiano(hz(m), 3.0), end_at, 0.14)
    n = int(total * SR)
    L, R = L[:n], R[:n]
    t = np.arange(n) / SR
    fade = np.clip((total - t) / out_fade, 0, 1) * np.clip(t / 0.3, 0, 1)
    return np.stack([L * fade, R * fade], axis=1)


def ambience(dur=6.0):
    """Restaurant room tone: low murmur + a few glass/cutlery clinks."""
    n = int(dur * SR)
    murmur = onepole_lp(np.cumsum(rng.uniform(-1, 1, n)) * 0.02, 600)
    murmur -= onepole_lp(murmur, 120)
    murmur *= 1 + 0.4 * np.sin(np.arange(n) / SR * 2 * np.pi * 0.7)
    out = murmur / (np.max(np.abs(murmur)) or 1) * 0.35
    for _ in range(9):
        at = rng.uniform(0.2, dur - 0.5)
        f = rng.uniform(2800, 5200)
        t = np.arange(int(0.35 * SR)) / SR
        clink = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.48 * t)) * np.exp(-t * 18)
        add(out, clink, at, rng.uniform(0.05, 0.13))
    return out


def ding():
    t = np.arange(int(1.6 * SR)) / SR
    x = np.sin(2 * np.pi * 1760 * t) + 0.45 * np.sin(2 * np.pi * 4300 * t) * np.exp(-t * 6)
    return x * np.exp(-t * 2.8) * np.minimum(1, t * 2000)


def tap():
    t = np.arange(int(0.12 * SR)) / SR
    return np.sin(2 * np.pi * (1300 + 900 * np.exp(-t * 60)) * t) * np.exp(-t * 45)


def whoosh(dur=0.7):
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = rng.uniform(-1, 1, n)
    env = np.sin(np.pi * t / dur) ** 2
    lo = onepole_lp(noise, 900)
    hi = noise - onepole_lp(noise, 3000)
    sweep = t / dur
    return (lo * (1 - sweep) + hi * sweep * 0.6) * env


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    radio_len = float(sys.argv[2]) if len(sys.argv) > 2 else 31.0
    write(out / "music_radio.wav", music(radio_len))
    write(out / "music_tv.wav", music(30.0))
    write(out / "amb.wav", ambience())
    write(out / "ding.wav", ding())
    write(out / "tap.wav", tap())
    write(out / "whoosh.wav", whoosh())
    print("ok")
