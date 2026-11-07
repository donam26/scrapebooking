"""Chụp dashboard demo (tenant video, `make demo-video-db`) cho video giới thiệu.

Mỗi trạng thái màn hình là một ảnh PNG độ nét gấp đôi (viewport 1440×900, DPR 2) kèm toạ độ các
vùng cần phóng to/tô sáng (px CSS của trang) trong `assets/shots/boxes.json`. Video dựng ở
`stage.html` đọc hai thứ này.

Dùng: backend/.venv/bin/python marketing/product-video/capture.py  (API :8002 + dashboard :3200)
"""

import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import Page, async_playwright

BASE = "http://localhost:3200"
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets" / "shots"
SEED = ROOT.parents[1] / "backend" / "scripts" / "seed_video_demo.py"
VIEWPORT = {"width": 1440, "height": 900}

# Toạ độ một phần tử (px CSS của cả trang). `card`: leo lên khung thẻ gần nhất (rounded + border).
BOX_JS = """
([sel, text, mode]) => {
  // Không phân biệt hoa thường: tiêu đề khối viết hoa bằng CSS (text-transform).
  const norm = s => s.trim().toLowerCase(), want = text === null ? null : norm(text);
  const all = [...document.querySelectorAll(sel)];
  let el = all.find(e => want === null || norm(e.textContent) === want)
        || all.find(e => want !== null && norm(e.textContent).includes(want));
  if (!el) return null;
  if (mode === 'rounded') {  // thẻ bo góc gần nhất (VD thẻ sự kiện trên lịch 12 tháng)
    while (el.parentElement && !/rounded/.test(el.className)) el = el.parentElement;
  }
  if (mode === 'card') {
    while (el.parentElement && !(/rounded/.test(el.className) && /border/.test(el.className))) {
      el = el.parentElement;
    }
  }
  const r = el.getBoundingClientRect();
  return {x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height};
}
"""

# Thẻ gợi ý giá (<article>) của một đêm trên "Việc cần làm hôm nay".
ARTICLE_JS = """
(text) => {
  const a = [...document.querySelectorAll('article')]
    .find(e => e.textContent.includes(text) && e.textContent.includes('Tôi đã đổi giá'));
  const r = a.getBoundingClientRect();
  return {x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height};
}
"""

# Cột của một đêm trong bảng lịch: từ ô tiêu đề tới hàng cuối của bảng.
COLUMN_JS = """
(label) => {
  const th = [...document.querySelectorAll('thead th')].find(e => e.textContent.includes(label));
  const table = th.closest('table');
  const a = th.getBoundingClientRect(), t = table.getBoundingClientRect();
  return {x: a.x + scrollX, y: a.y + scrollY, w: a.width, h: t.bottom - a.top};
}
"""

# Các ô "HẾT" (hết phòng) trong cột của một đêm.
SOLD_JS = """
(label) => {
  const ths = [...document.querySelectorAll('thead th')];
  const idx = ths.findIndex(e => e.textContent.includes(label));
  return [...document.querySelectorAll('tbody tr')].map(tr => tr.children[idx])
    .filter(td => td && /HẾT|Hết/.test(td.textContent))
    .map(td => { const r = td.getBoundingClientRect();
                 return {x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height}; });
}
"""


async def box(page: Page, sel: str, text: str | None = None, mode: str = "el") -> dict:
    found = await page.evaluate(BOX_JS, [sel, text, mode])
    if found is None:
        raise RuntimeError(f"không thấy {sel!r} {text!r}")
    return found


async def shot(page: Page, name: str) -> None:
    await page.wait_for_timeout(600)
    await page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    size = await page.evaluate(
        "[document.documentElement.scrollWidth, document.documentElement.scrollHeight]"
    )
    print(f"  {name}.png {size[0]}×{size[1]}")


async def goto(page: Page, path: str) -> None:
    await page.goto(f"{BASE}{path}", wait_until="networkidle")
    await page.wait_for_timeout(800)


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seed = SEED.read_text(encoding="utf-8")
    email = re.search(r'^EMAIL = "(.+)"', seed, re.M).group(1)
    password = re.search(r'^PASSWORD = "(.+)"', seed, re.M).group(1)
    boxes: dict[str, object] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport=VIEWPORT, device_scale_factor=2, locale="vi-VN")
        page = await ctx.new_page()
        await goto(page, "/login")
        await page.fill('input[type="email"]', email)
        await page.fill('input[type="password"]', password)
        await page.keyboard.press("Enter")
        await page.wait_for_url("**/today")
        await page.wait_for_load_state("networkidle")

        # Hôm nay: thẻ gợi ý thứ Bảy, nút ghi quyết định, nhãn độ mới dữ liệu.
        await goto(page, "/today")
        await shot(page, "today")
        hero = await page.evaluate(ARTICLE_JS, "31/10")
        boxes["today"] = {
            "hero_card": hero,
            "tonight_card": await page.evaluate(ARTICLE_JS, "Đêm nay"),
            "hero_reason": await box(
                page, "span, p, div", "4/6 đối thủ đã hết hoặc chỉ còn ≤3 phòng"
            ),
            "fresh": await box(page, "header span", "Cập nhật 06:00 hôm nay"),
            "strip": await box(page, "h2, h3, div, span", "14 ĐÊM TỚI: BẠN SO VỚI ĐỐI THỦ", "card"),
        }
        buttons = page.get_by_role("button", name="Tôi đã đổi giá")
        apply_btn = buttons.nth(1)  # thẻ thứ hai = thứ Bảy (thẻ đầu là đêm nay)
        b = await apply_btn.bounding_box()
        scroll = await page.evaluate("[scrollX, scrollY]")
        boxes["today"]["hero_apply"] = {
            "x": b["x"] + scroll[0],
            "y": b["y"] + scroll[1],
            "w": b["width"],
            "h": b["height"],
        }
        await apply_btn.click()
        await page.wait_for_timeout(700)
        confirm = page.get_by_role("button", name="Xác nhận")
        if await confirm.count():
            await shot(page, "today_dialog")
            c = await confirm.first.bounding_box()
            boxes["today"]["dialog_confirm"] = {
                "x": c["x"] + scroll[0],
                "y": c["y"] + scroll[1],
                "w": c["width"],
                "h": c["height"],
            }
            await confirm.first.click()
            await page.wait_for_timeout(900)
        await shot(page, "today_applied")
        boxes["today"]["applied_row"] = await box(
            page, "span, div, p", "Đã ghi: bạn đã đổi giá", "card"
        )
        undo = page.get_by_role("button", name="Hoàn tác")
        if await undo.count():
            await undo.first.click()  # trả dữ liệu demo về như cũ cho lần quay sau
            await page.wait_for_timeout(700)

        # Lịch giá & phòng: ba chế độ, cột thứ Bảy, hàng của bạn.
        await goto(page, "/calendar")
        cal = {
            "sat_col": await page.evaluate(COLUMN_JS, "31/10"),
            "tonight_col": await page.evaluate(COLUMN_JS, "24/10"),
            "sat_sold": await page.evaluate(SOLD_JS, "31/10"),
        }
        own = await page.evaluate(
            """() => { const tr = [...document.querySelectorAll('tbody tr')]
                         .find(e => e.textContent.includes('Của tôi'));
                       const r = tr.getBoundingClientRect();
                       return {x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height}; }"""
        )
        cal["own_row"] = own
        for label, key in (("Phòng còn", "rooms"), ("Giá", "price"), ("Chênh với bạn", "diff")):
            btn = page.locator("button").filter(has_text=re.compile(rf"^\s*{label}\s*$")).first
            bb = await btn.bounding_box()
            cal[f"btn_{key}"] = {"x": bb["x"], "y": bb["y"], "w": bb["width"], "h": bb["height"]}
            await btn.click()
            await page.wait_for_timeout(500)
            await shot(page, f"calendar_{key}")
        boxes["calendar"] = cal
        await page.locator("button").filter(has_text=re.compile(r"^\s*Phòng còn\s*$")).first.click()

        # Thị trường: hàng mức căng 14 đêm, khối hôm nay, lịch sự kiện.
        await goto(page, "/market")
        await shot(page, "market")
        boxes["market"] = {
            "tension": await box(page, "h2, h3, div, span", "MỨC CĂNG KHU VỰC 14 ĐÊM TỚI", "card"),
            "today_area": await box(page, "h2, h3, div, span", "HÔM NAY TRONG KHU VỰC", "card"),
            "events": await box(
                page, "h2, h3, div, span", "LỊCH SỰ KIỆN & NGÀY LỄ 12 THÁNG", "card"
            ),
            "sat_col": await page.evaluate(COLUMN_JS, "31/10"),
            "conference": await box(page, "div, span, p", "Hội nghị Y khoa quốc tế", "rounded"),
        }

        await goto(page, "/competitors")
        await shot(page, "competitors")
        await browser.close()
    (OUT / "boxes.json").write_text(json.dumps(boxes, ensure_ascii=False, indent=1), "utf-8")
    print("boxes.json ok")


if __name__ == "__main__":
    asyncio.run(main())
