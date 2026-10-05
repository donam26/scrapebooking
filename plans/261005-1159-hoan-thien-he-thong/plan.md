# Plan hoàn thiện hệ thống OTARadar (sau audit 2026-10-05)

Nguồn: `plans/reports/audit-261005-1159-he-thong-tung-luong-diem-manh-yeu-do-sau.md`. Mục tiêu: đưa hệ thống từ
"chạy được cho tenant thử nghiệm" (độ sâu 3,0/5) lên "bán được cho khách trả tiền, vận hành không cần người canh"
(≥4/5 ở mọi luồng), **không thêm tính năng mới cho tới khi dữ liệu đúng và vận hành an toàn**.

Nguyên tắc: sửa gốc, không "enhanced" file; mỗi phase kết thúc bằng CI xanh + tiêu chí nghiệm thu đo được; YAGNI với
mọi thứ chưa có khách đòi (Traveloka/Expedia, Zalo, self-serve, ML).

## Phase

| # | Phase | Mục tiêu | Ước lượng (1 senior) | Phụ thuộc | Trạng thái |
|---|---|---|---|---|---|
| 0 | [Khôi phục nền & hygiene](phase-00-khoi-phuc-nen-ci-hygiene.md) | CI main xanh, script onboarding chạy, repo sạch, rules đúng stack | 1–2 ngày | — | todo |
| 1 | [Đúng dữ liệu](phase-01-dung-du-lieu-collector-analytics-insight.md) | Giá/tồn kho/sự kiện/bản tin đúng; soft-block không giết listing | 1–1,5 tuần | 0 | todo |
| 2 | [Bảo mật & vận hành sản xuất](phase-02-bao-mat-va-van-hanh-san-xuat.md) | Không secret mặc định, không cổng mở, TLS, backup offsite, alert, HA scheduler | 1,5–2 tuần | 0 | todo |
| 3 | [Hiệu năng & dữ liệu](phase-03-hieu-nang-index-retention-run-lifecycle.md) | Index hot path, vòng đời run kín, retention, N+1, budget ưu tiên | 1 tuần | 1, 2 | todo |
| 4 | [Chất lượng FE & test](phase-04-chat-luong-dashboard-va-test.md) | FE có test, data layer có cache, TZ nhất quán, contract test kênh | 1 tuần | 0 | todo |
| 5 | [Hoàn thiện chức năng còn mở](phase-05-hoan-thien-chuc-nang-con-mo.md) | Đóng mục "còn để ngỏ" trong docs; tính năng theo quyết định nghiệp vụ | 2–4 tuần (tuỳ chọn) | 1–4 | todo |

Tổng tới "production-ready v1" (phase 0–4): **6–8 tuần** một senior, hoặc ~4 tuần nếu phase 2 và 4 chạy song song
(2 người, ranh giới file rõ: 2 = backend/infra, 4 = dashboard/tests).

## Thứ tự và lý do
1. Phase 0 trước mọi thứ: không có CI xanh thì không có bằng chứng cho bất kỳ phase nào.
2. Phase 1 trước phase 2: sửa dữ liệu cần `reparse` HTML thô còn trong MinIO (giữ 30 ngày) → càng muộn càng mất
   lịch sử để tính lại.
3. Phase 2 là điều kiện **bán hàng**: secret mặc định + cổng DB mở là blocker tuyệt đối.
4. Phase 3 trước khi tenant thứ 5–10: index `room_snapshots(probe_id)` là thứ đầu tiên sập khi dữ liệu lớn.
5. Phase 4 song song được; phase 5 chỉ sau khi có câu trả lời ở mục "Câu hỏi" (audit §4).

## Tiêu chí nghiệm thu toàn plan
- `make lint typecheck test-int` + `npm run lint typecheck build i18n:check` + FE test xanh trên CI `main`.
- `scripts/validate_run.py` 0 sai lệch trên 1 run thật mỗi kênh sau phase 1; không `price_up/down` giả trên đêm min-LOS>1.
- Startup từ chối `JWT_SECRET` mặc định; `nmap` VPS chỉ thấy 80/443; restore backup từ máy khác thành công trong 30 phút.
- 100 khách sạn × 5 kênh × 3 lượt chạy 7 ngày: không run `partial` vì deadline, p95 ghi probe < 50 ms, analytics
  < 2 phút/run, không alert thiếu.
- Mọi mục "Điều còn để ngỏ" trong `docs/user-flows.md` được đóng hoặc ghi rõ lý do hoãn.

## Không làm trong plan này (YAGNI, chờ khách đòi)
Traveloka/Expedia (cần proxy uy tín cao), Zalo OA/ZNS, self-serve + billing đầy đủ, ML forecast, map loại phòng chéo
kênh, đa occupancy/LOS, chuyển k8s, Google Hotels/SerpApi, ảnh chụp bằng chứng.

## Câu hỏi chưa giải quyết
Xem audit §4 (8 câu). Câu 1 (giá Booking đa đêm) và 4 (mục tiêu triển khai) ảnh hưởng trực tiếp phase 1 và 2;
có thể bắt đầu phase 0 ngay không cần trả lời.
