# Phase 3: Rule cảnh báo + gửi email + màn Thông báo

Trạng thái: done · Effort: M

## Mô hình dữ liệu (migration `0006_notifications`)
- `notification_recipients`: id, tenant_id, email, active, created_at; unique (tenant_id, lower(email)).
- `notification_rules`: tenant_id + kind (PK), active, params JSONB, updated_at. Một dòng mỗi loại.
- `notifications` (outbox + nhật ký): id, tenant_id, kind, dedupe_key UNIQUE, subject, body_text, body_html, recipients JSONB, status (`sent` | `failed` | `skipped`), detail, created_at, sent_at, scan_run_id?, insight_id?.

## Loại thông báo (`NotificationKind`)
| kind | Kích hoạt | Tham số mặc định |
|---|---|---|
| `daily_insight` | Bản tin daily `completed` | — (mặc định bật) |
| `weekly_report` | Thứ Hai 08:00 giờ tenant (phase 4) | — (mặc định bật) |
| `competitor_sold_out` | Sự kiện `sold_out` của đối thủ trong lượt quét, đêm trong N đêm tới, và số đối thủ hết đêm đó ≥ M | within_days 14, min_sold_out 1 |
| `competitor_low_stock` | Sự kiện `low_stock_enter` của đối thủ | within_days 7 |
| `competitor_price_drop` | Sự kiện `price_down` của đối thủ với mức giảm ≥ X% | within_days 14, min_pct 10 |

Rule chưa có dòng trong DB = dùng mặc định (bật). Chỉ sự kiện của đối thủ trong watchlist active.

## Gửi
- `app/notify/`:
  - `rules.py` (thuần): sự kiện + compset + rule → danh sách mục cảnh báo.
  - `render.py` (thuần): subject + text + HTML (inline style, màu thương hiệu) cho cảnh báo, bản tin, báo cáo tuần; liên kết sâu `APP_BASE_URL`.
  - `email_sender.py`: `SmtpEmailSender` (stdlib `smtplib` qua `asyncio.to_thread`, STARTTLS hoặc SSL); không cấu hình `SMTP_HOST` → không gửi, dòng nhật ký `skipped` "chưa cấu hình máy chủ email".
  - `service.py`: `NotificationService` với outbox: chèn dòng theo `dedupe_key` (ON CONFLICT DO NOTHING) → chỉ gửi khi chèn được → cập nhật trạng thái. Mỗi người nhận một email (không lộ địa chỉ nhau).
- Cron `dispatch_notifications` mỗi 5 phút ở jobs worker, idempotent, tự bù khi worker tắt:
  - lượt quét đã analytics trong 24 giờ qua × tenant → `alert:{tenant}:{run}` (một email gom mọi mục; không có mục → `skipped`, không gửi).
  - bản tin daily `completed` trong 24 giờ qua → `insight:{insight_id}`.
- Config: `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SECURITY` (`starttls`|`ssl`|`none`), `APP_BASE_URL`.

## API (`/notifications`, tenant)
- `GET /notifications/settings` → `{email_configured, recipients[], rules[]}`.
- `POST /notifications/recipients`, `DELETE /notifications/recipients/{id}` (tenant_admin).
- `PUT /notifications/rules/{kind}` `{active, params}` (tenant_admin; kiểm tra miền giá trị).
- `POST /notifications/test` (tenant_admin): gửi email thử, giới hạn 1 lần/phút/tenant.
- `GET /notifications/log?limit=50`: nhật ký gần đây; `detail` kỹ thuật chỉ operator thấy.

## Dashboard: Cài đặt → tab "Thông báo"
- Thẻ "Người nhận email": danh sách + ô thêm + xoá; nút "Gửi thử"; ghi chú cảnh báo khi máy chủ email chưa cấu hình ("liên hệ đơn vị vận hành").
- Thẻ "Gửi gì": mỗi loại một hàng: công tắc + câu mô tả có ô số nội tuyến ("Đối thủ giảm giá từ [10]% cho một đêm trong [14] đêm tới"), lưu theo hàng.
- Thẻ "Đã gửi gần đây": bảng thời gian · loại · tiêu đề · nhãn trạng thái.
- Viewer chỉ xem.

## Kiểm thử
- Unit: rules (ngưỡng, cửa sổ ngày, chỉ đối thủ), render (không lộ token/mã lượt quét), sender null.
- Integration: API CRUD + phân quyền; dispatch idempotent (chạy 2 lần gửi 1 lần) với sender giả.

## Tiêu chí xong
Sau một lượt quét có đối thủ hết phòng → đúng một email gom tới mỗi người nhận; chạy lại cron không gửi trùng.
