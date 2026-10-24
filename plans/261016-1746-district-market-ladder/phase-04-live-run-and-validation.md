# Pha 4 — Proxy mới, quét thật, đối chiếu, tài liệu

## Việc
1. Proxy: `.env` `PROXY_URL_TEMPLATE=http://<user>:<pass>@14.224.225.153:24767` (host:port:user:pass của người dùng; `.env` không commit). `sb check-proxy` → ok (exit IP VN).
2. DB dev: backup `pg_dump -Fc` → `alembic upgrade head` (0016 → 0018).
3. Chạy API (:8001) + worker Booking trên host (Redis db 1, tránh đụng stack Docker) với code mới.
4. Tenant 9 (Rex, Q1): tạo khu vực
   - "Quận 1" — district 2088, phân khúc KS + resort + căn hộ KS, `detail_max_hotels=0`;
   - "3 km quanh Rex" — latlong (10.77574, 106.70141), `radius_m=3000`, cùng phân khúc, `detail_max_hotels=0`.
   "Quét ngay" → theo dõi log/DB: đủ 14 đêm, request/đêm, không bị chặn.
5. Kiểm API + UI (dashboard :3100 → :8001), ảnh chụp vi/en, desktop + 390 px.
6. Đối chiếu: `scripts/validate_market_ladder.py` — so `rooms_min` (thang tìm kiếm) với `hotel_calendars.rooms_min/rooms_max` (thang lịch) + sàn trang của compset trên cùng đêm; cần một lượt quét compset (`sb scan-now`) cùng ngày.
7. Docs: `docs/operations.md` (thị trường khu vực v2, proxy), `PRODUCT.md` (năng lực), cập nhật plan.

## Xong khi
Dữ liệu thật trong DB + API + UI; báo cáo đối chiếu trong `reports/`; plan cập nhật kết quả.
