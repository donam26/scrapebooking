"""Render video OTARadar: stage.html → khung hình → MP4 H.264 + âm thanh.

Dùng (Python có Playwright, VD backend/.venv/bin/python):
  render.py --stills 3,12,30   ảnh tĩnh ở các giây để duyệt nhanh (out/stills/)
  render.py                    video đầy đủ out/otaradar-gioi-thieu.mp4
  render.py --no-subs          bản không phụ đề

Cần trước: capture.py (ảnh dashboard), voiceover.py (giọng đọc + timeline). Âm thanh: soundtrack.py
được gọi ở đây sau khi lấy mốc click/chuyển cảnh từ stage.
"""

import asyncio
import functools
import http.server
import json
import math
import subprocess
import sys
import threading
import time
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
FPS = 30
WORKERS = 4


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

    handler = functools.partial(Quiet, directory=str(ROOT))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


async def open_stage(browser, port: int, subs: bool):
    page = await browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    await page.goto(f"http://127.0.0.1:{port}/stage.html", wait_until="networkidle")
    await page.wait_for_function("window.__ready === true", timeout=60000)
    if not subs:
        await page.add_style_tag(content="#subs{display:none!important}")
    return page


async def frame(page, t: float) -> bytes:
    await page.evaluate(f"window.seek({t:.4f})")
    return await page.screenshot(type="jpeg", quality=95)


async def render_range(browser, port: int, subs: bool, first: int, last: int, path: Path) -> None:
    page = await open_stage(browser, port, subs)
    enc = subprocess.Popen(  # noqa: ASYNC220 — script render một lần, ffmpeg chạy song song là đủ
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "image2pipe",
            "-framerate",
            str(FPS),
            "-c:v",
            "mjpeg",
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "15",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            str(path),
        ],
        stdin=subprocess.PIPE,
    )
    for i in range(first, last):
        enc.stdin.write(await frame(page, i / FPS))
    enc.stdin.close()
    enc.wait()
    await page.close()


def mix_audio(video: Path, out: Path) -> None:
    a = ROOT / "assets"
    graph = (
        "[1:a]aresample=48000,asplit=2[v][key];"
        "[2:a]aresample=48000,volume=0.55[m];"
        "[m][key]sidechaincompress=threshold=0.015:ratio=10:attack=15:release=450:makeup=1[md];"
        "[3:a]aresample=48000,volume=0.4[s];"
        "[v][md][s]amix=inputs=3:normalize=0,"
        "loudnorm=I=-16:LRA=11:TP=-1.5,aformat=channel_layouts=stereo[aout]"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-i",
            str(a / "vo" / "voice.wav"),
            "-i",
            str(a / "music.wav"),
            "-i",
            str(a / "sfx.wav"),
            "-filter_complex",
            graph,
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out),
        ],
        check=True,
    )


async def main() -> None:
    args = sys.argv[1:]
    subs = "--no-subs" not in args
    srv, port = serve()
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--disable-gpu-vsync"])
        if "--stills" in args:
            times = [float(x) for x in args[args.index("--stills") + 1].split(",")]
            page = await open_stage(browser, port, subs)
            (OUT / "stills").mkdir(exist_ok=True)
            for t in times:
                await page.evaluate(f"window.seek({t})")
                await page.screenshot(path=str(OUT / "stills" / f"t{t:06.2f}.png"))
            print(f"{len(times)} ảnh → out/stills/")
            await browser.close()
            srv.shutdown()
            return

        page = await open_stage(browser, port, subs)
        duration = await page.evaluate("window.__duration")
        cues = await page.evaluate("window.__cues")
        await page.close()
        (ROOT / "assets" / "cues.json").write_text(json.dumps(cues, indent=1), "utf-8")
        snd = subprocess.Popen([sys.executable, str(ROOT / "soundtrack.py")])  # noqa: ASYNC220 — script render một lần, ffmpeg chạy song song là đủ

        total = math.ceil(duration * FPS)
        size = math.ceil(total / WORKERS)
        parts = [OUT / f"part{i}.mp4" for i in range(WORKERS)]
        started = time.time()
        await asyncio.gather(
            *(
                render_range(browser, port, subs, i * size, min(total, (i + 1) * size), parts[i])
                for i in range(WORKERS)
            )
        )
        print(f"{total} khung hình trong {time.time() - started:.0f}s")
        await browser.close()
    srv.shutdown()

    listing = OUT / "parts.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), "utf-8")
    silent = OUT / "video-silent.mp4"
    subprocess.run(  # noqa: ASYNC221 — script render một lần, ffmpeg chạy song song là đủ
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            str(silent),
        ],
        check=True,
    )
    if snd.wait() != 0:
        raise SystemExit("soundtrack.py lỗi")
    name = "otaradar-gioi-thieu.mp4" if subs else "otaradar-gioi-thieu-khong-phu-de.mp4"
    mix_audio(silent, OUT / name)
    for p in [*parts, listing, silent]:
        p.unlink()
    print(f"→ out/{name}")


if __name__ == "__main__":
    asyncio.run(main())
