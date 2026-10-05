# Báo cáo triển khai: đa kênh OTA (D1–D12)

Ngày: 2026-10-01, 14:41–17:15. Trạng thái: **đã deploy lên stack Docker local, đang quét thật tenant 9 trên 5 kênh**. Chưa commit (giống wave1/wave2).

## 1. Kết quả theo kênh (chạy thật qua proxy VN `160.250.166.88:20789`)

| Kênh | Lượt đầu (run) | Cách thu | Tồn phòng | Ghi chú |
|---|---|---|---|---|
| Booking.com | 370/370 ok (#28) | Playwright cookie + curl_cffi HTML, calendar GraphQL | exact (badge) / capped (dropdown 10) | thêm cờ thuế, giá gạch, nhãn KM (parser v5) |
| Agoda | 360/360 ok (#27) | curl_cffi JSON `GetSecondaryData`, header `cr-currency-code: VND` | exact theo loại phòng | giá gốc = trước coupon/campaign Agoda; `bookings_today`, `bookings_24h` |
| iVIVU | lỗi ghi DB ở #29 → sửa (0009, parser v2) → chạy lại #36 | Chromium mới (token `X-ivv-key` dùng 1 lần) + curl_cffi JSON | không công bố (hidden) | `source_supplier` mỗi giá (AGODA/MGB/HBED/B2B/IVIVU); `rooms_sold_24h`, `bookings_month` |
| Trip.com | 360/360 ok (#31, 53 phút, 2 worker) | Chromium mở trang (token chống bot) | capped (theo giá) | gói khách sạn tính giá, combo bay loại; `last_booked_minutes` |
| Mytour | 270/270 ok (#30) | curl_cffi JSON `apis.tripi.vn` + `appHash` | capped (theo giá) | giá đại lý `ta:*` giữ (lộ giá sỉ); hiển thị "đặt N giờ trước" bị chia 5 → lưu phút thật |
| Traveloka | — | — | — | DataDome chặn cả Chrome thật + chặn IP. Chỉ nhận diện URL |
| Expedia | — | — | — | Akamai 429. Chỉ nhận diện URL |

Gợi ý chéo kênh trên tenant 9: 17 gợi ý trong 45 giây; 15 khớp 1,0 đã xác nhận (operator), 2 chờ người dùng (The Reverie Agoda 0,88; Meander Mytour 0,80).

Phát hiện nghiệp vụ đầu tiên: **Rex bị bán qua đại lý trên Mytour 3.781.000 ₫ cố định mọi đêm**, trong khi Booking 4,06–4,77 tr, Agoda 5,2–6,1 tr (sự kiện `parity_gap`).

## 2. Đã làm
- Phase 1–10 theo `plan.md`. Migration 0007 (listings, channel, demand signals, reference_channel, horizon 90), 0009 (external_room_id 200). 0008 là của phiên wave2.
- Khoá listing = (hotel_id, channel); run = (mốc × kênh); hàng đợi + worker riêng mỗi kênh; ngân sách request/phút theo kênh (Redis); tự ngắt kênh khi chặn >20%/15'; kiểm tra proxy 15'; cảnh báo operator qua email (`OPS_ALERT_EMAILS`); `run_summary_alert` báo cả run 0 probe.
- Analytics theo kênh + `channel_closed`, `parity_gap` (chỉ khách sạn "của bạn"); email gộp mọi kênh của một mốc, chỉ giữ kênh rẻ nhất cho parity; luật `own_parity_gap`; bản tin AI prompt v2 (đa kênh, `demand:<id>`).
- API: URL mọi kênh, `/channels` (hosts), listing confirm/reject/pause/resume/retry, discover, `?channel=` cho overview/hotel/day/events/CSV, dải `channels` ở chi tiết đêm (`tax_inclusive`), demand signals.
- Dashboard: form URL đa kênh, chip kênh + gợi ý, bộ chọn kênh, "So kênh" (đánh dấu rẻ nhất chỉ giữa kênh gồm thuế), tín hiệu cầu, cột/lọc kênh sự kiện, luật parity, kênh tham chiếu.
- Docs: PRODUCT.md, docs/operations.md, docs/user-flows.md §G, .env.example.

## 3. Kiểm chứng
- Backend: **610 test** pass (unit + integration, Postgres :55432), ruff/format/mypy sạch. Dashboard: typecheck + lint pass; ảnh chụp thật trang Cài đặt/Chi tiết đêm (`scratchpad/ui/prod-*.png`).
- Lỗi chỉ lộ ra khi chạy thật, đã sửa + test hồi quy: iVIVU `Isshowprices=0` làm cả khách sạn "hết phòng"; Mytour đêm sát ngày không "completed"; job listing không thử lại khi timeout mạng; `external_room_id` 32 ký tự; `parity_gap` sinh cho cả đối thủ (351 sự kiện/mốc → chỉ khách sạn của bạn).

## 3b. Review độc lập (code-reviewer) và sửa
- High: (1) tenant sửa được listing dùng chung → chỉ tenant theo dõi duy nhất hoặc operator được đổi URL/tạm dừng; cần link active; dán lại URL đang quét không reset. (2) email gửi trước khi mọi kênh của mốc có analytics → đợi đủ (tối đa 2h). (3) listing bị dừng/xoá sau khi tạo run làm job kẹt tới hạn chót → job chốt `listing_inactive` ngay.
- Medium/low đã sửa: chéo kênh đánh giá đối xứng trong cùng mốc (3h) và gắn đúng kênh; bỏ gợi ý giữ dòng `rejected`; `last_error` chỉ mã lỗi; `ProxyEndpoint` ẩn mật khẩu/URL khỏi repr; URL chữ số Unicode/quá dài → 422 thay vì 500; budget Redis INCR+EXPIRE nguyên tử; tạo listing đồng thời không 500; downgrade 0009 không xoá dữ liệu; ẩn trigger_key thủ công của tenant khác; verify không ghi đè `paused`.
- Không sửa (chấp nhận/ghi nhận): không có unique (channel, external_id) (đã check-then-act ở verify/discover); email một mốc chờ kênh chậm nhất (≤90'); hạn mức số khách sạn/tenant chưa có.
- Thêm theo dữ liệu thật: cảnh báo parity gộp theo (khách sạn, kênh): "Rex đang rẻ hơn 7%–21% trên Mytour ở 22 đêm".

Kết quả cuối: **613 test pass**, ruff/format/mypy sạch, dashboard typecheck/lint pass; lượt quét thứ hai theo tầng: Agoda 56/56, Booking 70/70, Mytour 42/42, Trip.com 48/56 (8 timeout do proxy nghẽn khi 3 trình duyệt chạy song song → giảm Trip.com về 1 worker), iVIVU quét bù 89/90.

**17:00 – iVIVU bắt đầu chặn**: sau ~420 probe/1,5h (quét bù đủ 90 đêm), run #36 có 18/29 `token_unavailable` → tự ngắt kênh kích hoạt đúng thiết kế (alert "[ivivu] Block rate 22%", dừng 30'), kênh khác không ảnh hưởng. `.env` thật chưa có `CHANNEL_BUDGETS` (mặc định 40/phút mọi kênh) → đặt `booking=40,agoda=30,ivivu=10,tripcom=20,mytour=20`. Cần theo dõi lượt 22:00 (chỉ ~14 đêm gần × 4 khách sạn).

## 4. Rủi ro / việc sau
- ToS: mọi kênh cấm scrape; iVIVU/Trip.com vượt token chống bot bằng trình duyệt (vùng xám hơn Booking). Agent Trip.com đã gửi ~1.000 request (vượt mức 150 đặt ra) khi spike.
- Khoá web Mytour (`appHash`) có thể đổi khi họ deploy → probe lỗi `api 3004`; canary/alert sẽ thấy.
- Trip.com nặng (20–45 s/probe, 1–2 MB): tối ưu đổi ngày trong trang nếu chậm/bị chặn.
- Chưa kiểm chứng: coupon Agoda thật; phản hồi hết phòng thật của iVIVU; `availability` Agoda có trần không (thấy 64).
- Việc sau (YAGNI lúc này): chế độ list (1 request nhiều khách sạn), `cross_refs` (iVIVU có sẵn mã Agoda → nối listing chắc chắn), map loại phòng chéo kênh, Traveloka (proxy uy tín cao/đối tác).

## 5. Câu hỏi chưa giải quyết
1. Email nhận cảnh báo vận hành (`OPS_ALERT_EMAILS`) và tài khoản SMTP?
2. Có đầu tư proxy dân cư uy tín cao/đối tác để mở Traveloka không?
3. Xác nhận 2 gợi ý còn chờ (The Reverie Agoda, Meander Mytour) trên giao diện.
4. Commit: tách theo đợt (wave1, wave2, đa kênh) khi bạn sẵn sàng.
