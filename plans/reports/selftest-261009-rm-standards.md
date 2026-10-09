# Self-test: roadmap chuẩn hoá RM (Phase 0–7), 09/10/2026

Plan: `plans/261009-1106-rm-standards-roadmap/plan.md` (bảng "Tình trạng triển khai" ở cuối).
Môi trường: stack Docker đang chạy (`scrapebooking-*`, Postgres :55432, Redis :6380), DB thật
đã backup trước khi migrate (`/tmp/sb_backup/scrapebooking_pre_rm_202610091238.dump`).

## 1. Kiểm tra tự động

| Hạng mục | Lệnh | Kết quả |
|---|---|---|
| Lint backend | `ruff check . && ruff format --check .` | sạch (278 file) |
| Kiểu backend | `mypy app` | 0 lỗi / 162 file |
| Test backend (unit + integration) | `pytest -m "not live"` trên DB test | **745 passed** |
| Test mới | `test_phase0_reliability`, `test_phase2_rate_shopping`, `test_phase3_notify`, `test_phase457_radar_otb`, `integration/test_rm_roadmap_api` | pass |
| OpenAPI | `scripts/export_openapi.py` + snapshot test | khớp; `api-types.ts` sinh lại |
| Dashboard | `tsc --noEmit`, `eslint`, `i18n:check`, `next build` | 0 lỗi; 2.509 khoá vi/en khớp; build 25 route |
| Migration DB thật | `alembic upgrade head` | 0011 → 0012 → 0013 → 0014 |
| Tính lại analytics | `sb analyze --reanalyze-days 20` | toàn bộ run 20 ngày, không lỗi |

## 2. Đo nhiễu sự kiện trước/sau (roadmap 2.9, mục tiêu O3)

`scripts/measure_event_noise.py --days 10` trên dữ liệu thật (5 kênh, 10 ngày):

| Chỉ số | Trước | Sau | Mục tiêu |
|---|---:|---:|---|
| `room_type_new/gone` | 8.621 | 367 (**−96%**) | giảm ≥70% ✅ |
| Đổi giá mức khách sạn | 1.193 | 654 (−45%) | — |
| …trong đó cùng loại phòng + cùng gói | 50–60% (theo kênh) | **100%** (theo định nghĩa mới) | ≥90% ✅ |
| Đổi giá mức loại phòng | 14.848 | 5.284 (−64%) | — |
| `lowest_rate_shift` (phòng/gói rẻ nhất hết hoặc mở lại) | — | 539 | tách khỏi "đổi giá" |

Booking: 71/112 lần "tăng giá" cũ thật ra là phòng rẻ nhất bán hết (`cheapest_gone`), khớp kết luận
C5 của báo cáo nghiên cứu. Parity trên dữ liệu thật giờ ghi nguyên nhân: 21 đêm iVIVU do KM khách sạn
"Ưu Đãi Đặc Biệt…" (−19,9%), 3 đêm do nguồn bán lại, 1 đêm Booking "Late Escape Deal".

## 3. Chạy trên stack thật (API :8000, dashboard build chạy tạm :3100)

- **Proxy 407 vẫn còn** (`sb check-proxy`: `#1 160.250.166.88:20084 FAIL 407`). Scheduler mới:
  báo "All proxies failing… scans are deferred", **hoãn mốc 14:00** (`scan_slot_deferred`), không
  tạo run rỗng (trước đây: run #188, #190 với 0 probe). Cảnh báo kênh <80%/24h và "không có dữ
  liệu >10 giờ" bắn ngay khi khởi động. Tất cả chỉ ra log vì chưa có SMTP/webhook (`sb check-ops`
  thoát mã 1, đúng thiết kế).
- `GET /data-status`: Booking 99,6% / Agoda 30% / iVIVU 18% / Trip.com 31% / Mytour 31% (7 ngày),
  mọi kênh `stale`, lần thành công cuối 14:04–14:20 ngày 08/10. Dashboard hiện dải đỏ "không có dữ
  liệu mới quá 10 giờ" và "Dữ liệu mới nhất 14:20 hôm qua" (không còn "Cập nhật lúc" theo lượt rỗng).
- Tin `data_stale` cho tenant Rex được tạo, ghi `skipped/smtp_not_configured` (chờ SMTP).
- `sb canary`: độ phủ trường 24 giờ so 7 ngày ổn định, không báo trôi parser.
- 22 endpoint mới/đổi trả 200 với tenant Rex (dữ liệu thật); `area-scarcity` 404 có chủ đích
  (tenant chưa có khu vực thị trường). Compset 14 đêm: 4/4 đối thủ có giá (`sample=ok`), chỉ số giá
  niêm yết 43–87, 2 đêm của Rex là "hạn chế" (lịch Booking không nhận khách 14–15/10), 26 ô có KM.
- Excel rate shop tải được (3 trang: Giá đối thủ / Compset / Thay đổi); báo cáo tháng HTML mở được.
- UI (Playwright, 18 màn hình, gồm Radar, Chiến lược giá, chi tiết đêm): không lỗi JS, không lỗi
  5xx, **0 lần** xuất hiện "ADR compset", "RevPAR compset", "Dự báo cầu", "So cùng kỳ", "Toàn cảnh
  thị trường đêm nay". Hai 404 còn lại là `/market/city` và `area-scarcity` khi chưa có khu vực
  thị trường (hiện empty state).
- Sửa thêm trong lúc test: lọc sự kiện ở Cài đặt › Sự kiện gọi khoảng 430 ngày (API giới hạn 400 →
  422, lỗi có từ trước); chữ KM dài của iVIVU tràn cột ở bảng thay đổi; gợi ý giá mặc định kéo giá
  về trung vị đối thủ (nay dùng định vị thường ngày của khách sạn khi chưa đặt chiến lược, và không
  gợi ý giảm giá khi chưa có bằng chứng cầu yếu từ OTB/PMS).

## 4. Chưa đạt vì phụ thuộc bên ngoài

| Mục tiêu | Thiếu gì |
|---|---|
| O1 (≥95% probe, cảnh báo ≤15 phút, 0 `skipped`) | Gia hạn/sửa proxy hiện tại + nhà cung cấp thứ hai; SMTP thật (SPF/DKIM); `OPS_ALERT_EMAILS` hoặc `OPS_ALERT_WEBHOOK_URLS` |
| O4 (Zalo ≤5 phút) | OA doanh nghiệp xác thực, Zalo Cloud nạp trước, template ZNS duyệt (`ZALO_ZNS_*`) |
| O5 (OTB hằng ngày) | File OTB/đặt phòng thật từ PMS của khách (đường nhập đã test bằng CSV mẫu) |
