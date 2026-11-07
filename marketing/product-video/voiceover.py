"""Giọng đọc tiếng Việt cho video (OpenAI gpt-4o-mini-tts) và dòng thời gian từ độ dài thật.

Mỗi cảnh trong `scenes.json` đọc liền một file WAV (đủ ngữ cảnh để giữ đúng tiếng Việt); file được
chuyển ngược thành chữ (whisper-1 + gpt-4o-transcribe) để bắt lỗi phát âm và lấy mốc từng câu, lệch
nhiều thì đọc lại. Kết quả: `assets/vo/*.wav`, `assets/vo/voice.wav` (cả bài) và
`assets/timeline.json` (mốc từng cảnh/câu cho stage.html, nhạc, phụ đề). Khoá OPENAI_API_KEY đọc
từ `.env` ở gốc repo.

Dùng: python3 marketing/product-video/voiceover.py [--force | --redo grid,trust]
"""

import concurrent.futures as cf
import difflib
import json
import re
import subprocess
import sys
import unicodedata
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VO = ROOT / "assets" / "vo"
ENV = ROOT.parents[1] / ".env"
SAMPLE_RATE = 24000  # gpt-4o-mini-tts trả WAV 24 kHz mono
LEAD_IN = 0.3  # giây im trước giọng đọc của mỗi cảnh
TAIL = 0.6  # giây giữ hình sau câu cuối


def _key() -> str:
    m = re.search(r"^OPENAI_API_KEY=(.*)$", ENV.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip().strip('"')


def _post(url: str, data: bytes, content_type: str) -> bytes:
    req = urllib.request.Request(
        url, data=data, headers={"Authorization": f"Bearer {_key()}", "Content-Type": content_type}
    )
    return urllib.request.urlopen(req, timeout=120).read()


def tts(text: str, out: Path, voice: str, instructions: str) -> None:
    body = {
        "model": "gpt-4o-mini-tts",
        "voice": voice,
        "input": text,
        "instructions": instructions,
        "response_format": "wav",
    }
    out.write_bytes(
        _post(
            "https://api.openai.com/v1/audio/speech", json.dumps(body).encode(), "application/json"
        )
    )


def transcribe(path: Path) -> dict:
    """Chuyển ngược thành chữ kèm mốc từng đoạn (whisper-1, verbose_json)."""
    b = uuid.uuid4().hex
    fields = (
        ("model", "whisper-1"),
        ("language", "vi"),
        ("response_format", "verbose_json"),
        ("timestamp_granularities[]", "segment"),
    )
    parts = [
        f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, v in fields
    ]
    parts.append(
        f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n".encode()
        + path.read_bytes()
        + b"\r\n"
    )
    parts.append(f"--{b}--\r\n".encode())
    raw = _post(
        "https://api.openai.com/v1/audio/transcriptions",
        b"".join(parts),
        f"multipart/form-data; boundary={b}",
    )
    return json.loads(raw)


def _words(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s.lower().replace("chín mươi", "90"))
    s = s.replace("booking chấm com", "booking.com").replace("ô-tê-a ra-đa", "ota ra đa")
    s = s.replace("đê-mô", "demo").replace("otaradar", "ota ra đa").replace("ra-đa", "ra đa")
    return re.findall(r"[\wđ.]+", s)


def similarity(expected: str, heard: str) -> float:
    return difflib.SequenceMatcher(None, _words(expected), _words(heard)).ratio()


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


def check_text(path: Path) -> str:
    """Nghe ngược bằng mô hình thứ hai (gpt-4o-transcribe) để chấm chéo với whisper-1."""
    b = uuid.uuid4().hex
    parts = [
        f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, v in (("model", "gpt-4o-transcribe"), ("language", "vi"))
    ]
    parts.append(
        f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n".encode()
        + path.read_bytes()
        + b"\r\n"
    )
    parts.append(f"--{b}--\r\n".encode())
    raw = _post(
        "https://api.openai.com/v1/audio/transcriptions",
        b"".join(parts),
        f"multipart/form-data; boundary={b}",
    )
    return json.loads(raw)["text"]


def make_scene(job: tuple[Path, str, str, str, bool]) -> tuple[Path, float, dict]:
    """Đọc cả đoạn của một cảnh (đủ ngữ cảnh tiếng Việt, ngữ điệu liền mạch). TTS lúc đúng lúc
    lệch (đọc sai thanh, đôi khi lạc ngôn ngữ), nên đọc nhiều bản và chấm bằng hai mô hình nghe
    ngược; điểm của một bản là điểm thấp hơn trong hai. Giữ bản tốt nhất (tối đa 6 lần đọc)."""
    path, say, voice, instructions, force = job
    if path.exists() and not force:  # giữ bản đã duyệt, chỉ lấy lại mốc thời gian
        heard = transcribe(path)
        return path, similarity(say, heard["text"]), heard
    best: tuple[float, dict] = (-1.0, {})
    keep = path.with_suffix(".best")
    for _ in range(6):
        tts(say, path, voice, instructions)
        heard = transcribe(path)
        score = min(similarity(say, heard["text"]), similarity(say, check_text(path)))
        if score > best[0]:
            best = (score, heard)
            keep.write_bytes(path.read_bytes())
        if score >= 0.95:
            break
    path.write_bytes(keep.read_bytes())
    keep.unlink()
    return path, best[0], best[1]


def sentence_times(texts: list[str], heard: dict, total: float) -> list[tuple[float, float]]:
    """Mốc từng câu trong file của cảnh: theo đoạn của whisper khi khớp số câu, nếu không thì chia
    khoảng nói theo số ký tự."""
    segs = heard.get("segments") or []
    if len(segs) == len(texts) and all(
        abs(len(_words(s["text"])) - len(_words(t))) <= max(2, len(_words(t)) // 4)
        for s, t in zip(segs, texts, strict=True)
    ):
        return [(s["start"], min(s["end"], total)) for s in segs]
    a = segs[0]["start"] if segs else 0.0
    z = min(segs[-1]["end"], total) if segs else total
    sizes = [len(t) for t in texts]
    out, cur = [], a
    for n in sizes:
        d = (z - a) * n / sum(sizes)
        out.append((cur, cur + d))
        cur += d
    return out


def main() -> None:
    force = "--force" in sys.argv
    # --redo grid,trust: đọc lại riêng các cảnh này
    redo = set(sys.argv[sys.argv.index("--redo") + 1].split(",")) if "--redo" in sys.argv else set()
    cfg = json.loads((ROOT / "scenes.json").read_text(encoding="utf-8"))
    VO.mkdir(parents=True, exist_ok=True)
    jobs = [
        (
            VO / f"{si:02d}-{scene['id']}.wav",
            " ".join(x["say"] for x in scene["lines"]),
            cfg["voice"],
            cfg["instructions"],
            force or scene["id"] in redo,
        )
        for si, scene in enumerate(cfg["scenes"])
    ]
    results = {}
    with cf.ThreadPoolExecutor(5) as ex:
        for path, score, heard in ex.map(make_scene, jobs):
            flag = "" if score >= 0.93 else "  <-- kiểm tra"
            print(f"{path.name}: {score:.2f} {duration(path):.2f}s | {heard['text']}{flag}")
            results[path.name] = heard

    # Dòng thời gian: cảnh dài bằng max(min, giọng đọc + nghỉ).
    timeline, t, placed = [], 0.0, []
    for si, scene in enumerate(cfg["scenes"]):
        f = VO / f"{si:02d}-{scene['id']}.wav"
        d = duration(f)
        start = t + LEAD_IN
        times = sentence_times([x["say"] for x in scene["lines"]], results[f.name], d)
        lines = [
            {
                "start": round(start + a, 3),
                "end": round(start + b, 3),
                "text": x.get("show", x["say"]),
            }
            for x, (a, b) in zip(scene["lines"], times, strict=True)
        ]
        dur = max(scene["min"], LEAD_IN + d + TAIL)
        timeline.append(
            {
                "id": scene["id"],
                "start": round(t, 3),
                "dur": round(dur, 3),
                "voice": [round(start, 3), round(start + d, 3)],
                "lines": lines,
            }
        )
        placed.append((start, f))
        t += dur
    total = round(t, 3)
    (ROOT / "assets" / "timeline.json").write_text(
        json.dumps(
            {"total": total, "contact": cfg.get("contact", ""), "scenes": timeline},
            ensure_ascii=False,
            indent=1,
        ),
        "utf-8",
    )

    # Cả bài giọng đọc: đặt từng cảnh đúng mốc (adelay) rồi trộn.
    inputs, filters = [], []
    for i, (start, f) in enumerate(placed):
        inputs += ["-i", str(f)]
        ms = int(start * 1000)
        filters.append(f"[{i}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(placed)))
    filters.append(f"{mix}amix=inputs={len(placed)}:normalize=0,apad=whole_dur={total}[out]")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-ac",
            "1",
            "-ar",
            "48000",
            str(VO / "voice.wav"),
        ],
        check=True,
    )
    print(f"timeline: {len(timeline)} cảnh, tổng {total:.1f}s → assets/timeline.json, vo/voice.wav")


if __name__ == "__main__":
    main()
