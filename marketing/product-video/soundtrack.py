"""Nhạc nền + hiệu ứng âm thanh tự tổng hợp (không dùng nhạc có bản quyền).

Đọc `assets/timeline.json` (mốc cảnh) và `assets/cues.json` (click chuột, thông báo, chuyển cảnh do
`render.py` lấy từ stage). Ghi `assets/music.wav` (nhạc nền) và `assets/sfx.wav` (hiệu ứng),
24 kHz mono — `render.py` trộn với giọng đọc (nhạc tự hạ khi có giọng).

- Cảnh mở đầu (hook + pain): nền trầm hơi căng + tiếng đồng hồ tích tắc, dâng lên trước khi hiện
  sản phẩm.
- Từ cảnh giới thiệu: pad ấm Dmaj7 – Bm7 – Gmaj7 – Asus2 (96 BPM), bass, arpeggio nhẹ; kết bài ngân
  hợp âm chủ rồi tắt dần.
"""

import json
import math
import random
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
SR = 24000
BPM = 96
BEAT = 60 / BPM
CHORD_LEN = 8 * BEAT  # 2 ô nhịp mỗi hợp âm
TABLE = [math.sin(2 * math.pi * i / 4096) for i in range(4096)]


def midi(n: int) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


# MIDI: D3=50, F#3=54, A3=57, C#4=61, B2=47, G2=43, E3=52, A2=45
CHORDS = [
    (38, [50, 54, 57, 61, 64]),  # Dmaj9
    (35, [47, 50, 54, 57, 61]),  # Bm7(add9)
    (31, [43, 47, 50, 54, 57]),  # Gmaj7
    (33, [45, 47, 52, 57, 59]),  # Asus2
]


def osc(
    buf: array,
    start: float,
    dur: float,
    freq: float,
    amp: float,
    attack: float,
    release: float,
    harmonics=(1.0, 0.25, 0.08),
    detune: float = 0.0,
) -> None:
    """Cộng một nốt (sóng sin + bồi âm) với đường bao tuyến tính vào `buf`."""
    i0, n = int(start * SR), int(dur * SR)
    a, r = max(1, int(attack * SR)), max(1, int(release * SR))
    f = freq * (1 + detune)
    steps = [f * (h + 1) * 4096 / SR for h in range(len(harmonics))]
    phases = [random.random() * 4096 for _ in harmonics]
    for k in range(n):
        idx = i0 + k
        if idx >= len(buf):
            break
        env = min(1.0, k / a, (n - k) / r)
        s = 0.0
        for h, w in enumerate(harmonics):
            s += w * TABLE[int(phases[h] + steps[h] * k) & 4095]
        buf[idx] += amp * env * s


def pluck(buf: array, start: float, freq: float, amp: float, decay: float = 0.28) -> None:
    i0, n = int(start * SR), int(1.2 * SR)
    step, step2 = freq * 4096 / SR, 2 * freq * 4096 / SR
    for k in range(n):
        idx = i0 + k
        if idx >= len(buf):
            break
        env = math.exp(-k / (decay * SR)) * min(1.0, k / 60)
        buf[idx] += amp * env * (TABLE[int(step * k) & 4095] + 0.35 * TABLE[int(step2 * k) & 4095])


def noise_sweep(buf: array, start: float, dur: float, amp: float, rising: bool) -> None:
    """Gió (whoosh): nhiễu trắng qua bộ lọc thông thấp một cực có tần số cắt quét."""
    i0, n = int(start * SR), int(dur * SR)
    y = 0.0
    for k in range(n):
        idx = i0 + k
        if idx >= len(buf) or idx < 0:
            continue
        p = k / n
        cut = (0.02 + 0.5 * p) if rising else (0.5 - 0.45 * p)
        y += cut * (random.uniform(-1, 1) - y)
        env = math.sin(math.pi * p) ** 2 if not rising else p**2
        buf[idx] += amp * env * y


def tick(buf: array, at: float, amp: float, freq: float = 2600.0, decay: float = 0.012) -> None:
    i0 = int(at * SR)
    step = freq * 4096 / SR
    for k in range(int(0.08 * SR)):
        idx = i0 + k
        if idx >= len(buf):
            break
        env = math.exp(-k / (decay * SR))
        buf[idx] += amp * env * (TABLE[int(step * k) & 4095] + 0.4 * random.uniform(-1, 1))


def normalize(buf: array, peak: float) -> None:
    m = max(abs(x) for x in buf) or 1.0
    g = peak / m
    for i in range(len(buf)):
        buf[i] *= g


def write(path: Path, buf: array) -> None:
    pcm = array("h", (max(-32767, min(32767, int(x * 32767))) for x in buf))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main() -> None:
    random.seed(7)
    tl = json.loads((ASSETS / "timeline.json").read_text(encoding="utf-8"))
    cues = json.loads((ASSETS / "cues.json").read_text(encoding="utf-8"))
    total = tl["total"] + 0.5
    scenes = {s["id"]: s for s in tl["scenes"]}
    reveal = scenes["reveal"]["start"]
    cta = scenes["cta"]["start"]
    music = array("f", bytes(4 * int(total * SR)))
    sfx = array("f", bytes(4 * int(total * SR)))

    # Phần căng: drone D + A thấp, nốt cao mờ, tiếng đồng hồ mỗi giây, dâng nhiễu trước khi lộ diện.
    osc(music, 0.0, reveal + 0.4, midi(38), 0.22, 1.5, 0.6, (1.0, 0.5, 0.2))
    osc(music, 0.0, reveal + 0.4, midi(45), 0.18, 2.0, 0.6, (1.0, 0.3))
    osc(music, 2.0, reveal - 1.6, midi(69), 0.05, 3.0, 2.0, (1.0,), detune=0.002)
    for s in range(int(reveal)):
        tick(sfx, s + 0.15, 0.05 if s % 2 else 0.07)
    noise_sweep(sfx, reveal - 1.6, 1.6, 0.35, rising=True)

    # Phần chính: hợp âm 2 ô nhịp/lượt từ lúc lộ diện tới hết bài.
    t, ci = reveal, 0
    end = total - 0.3
    while t < end:
        root, notes = CHORDS[ci % len(CHORDS)]
        last = t + CHORD_LEN >= end
        dur = (end - t) if last else CHORD_LEN + 0.6
        for n in notes:
            for det in (-0.0018, 0.0018):
                osc(
                    music,
                    t,
                    dur,
                    midi(n),
                    0.045,
                    0.9,
                    1.6 if last else 0.9,
                    (1.0, 0.22, 0.06),
                    detune=det,
                )
        osc(music, t, dur, midi(root), 0.16, 0.08, 1.2 if last else 0.4, (1.0, 0.35, 0.1))
        # Arpeggio móc đơn (quãng 8 trên), thưa dần ở cảnh kêu gọi.
        arp = [notes[1] + 12, notes[2] + 12, notes[3] + 12, notes[4] + 12]
        steps = int(min(CHORD_LEN, end - t) / (BEAT / 2))
        for k in range(steps):
            at = t + k * BEAT / 2
            if at >= cta + 4 and k % 2:
                continue
            if at < reveal + 1.2:
                continue
            pluck(
                music, at, midi(arp[(k * 3) % 4] if k % 4 else arp[0]), 0.035 + 0.01 * (k % 2 == 0)
            )
        t += CHORD_LEN
        ci += 1

    # Hiệu ứng theo stage: click chuột, chuông thông báo, chuyển cảnh.
    for c in cues:
        if c["kind"] == "click":
            tick(sfx, c["t"], 0.22, 1500.0, 0.008)
        elif c["kind"] == "chime":
            pluck(sfx, c["t"], midi(88), 0.18, 0.35)
            pluck(sfx, c["t"] + 0.12, midi(93), 0.16, 0.5)
        elif c["kind"] == "whoosh":
            noise_sweep(sfx, c["t"] - 0.25, 0.55, 0.28, rising=False)

    # Tắt dần 2,5 giây cuối.
    fade = int(2.5 * SR)
    for k in range(fade):
        music[len(music) - fade + k] *= 1 - k / fade
    normalize(music, 0.9)
    normalize(sfx, 0.9)
    write(ASSETS / "music.wav", music)
    write(ASSETS / "sfx.wav", sfx)
    print(f"music.wav + sfx.wav {total:.1f}s")


if __name__ == "__main__":
    main()
