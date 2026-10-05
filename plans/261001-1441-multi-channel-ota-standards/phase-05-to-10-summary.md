# Phase 5–10
5. Worker theo kênh: `WORKER_CHANNEL` → queue `arq:queue:collector:<kênh>`; `app/collector/budget.py` (Redis fixed-window req/phút theo kênh); scheduler tự ngắt kênh (chặn >20%/15', min 20 probe) → Redis `channel_paused:<kênh>` 30', không tạo run kênh đó; docker compose `worker-<kênh>`.
6. Listing: API tạo listing `unverified` + job `verify_listing` (queue kênh); job `discover_listings(hotel_id)` gọi `suggest` các kênh khác → listing `suggested` (match_score); API xác nhận/bỏ.
7. Chéo kênh (sau analytics mỗi run): `channel_closed` (kênh này hết, kênh khác còn, quan sát ≤12h), `parity_gap` (khách sạn rẻ hơn ≥5% ở kênh này so với kênh tham chiếu, cùng cơ sở thuế); lưu `listing_demand_signals`; notify gộp theo khách sạn + loại `parity_gap` cho khách sạn self; insight thêm kênh + tín hiệu cầu.
8. Dashboard: form URL mọi kênh + gợi ý listing; chip kênh mỗi khách sạn; bộ chọn kênh ở overview/hotel/day; dải so kênh ở chi tiết đêm; cột kênh ở sự kiện; cài đặt kênh tham chiếu.
9. Tầng: 0–14 mọi lượt; 15–60 nếu lần dùng được gần nhất >20h; 61–90 nếu >66h.
10. Test, rebuild image, chạy thật tenant 9 (Rex + đối thủ + Melia qua ivivu), cập nhật PRODUCT.md, docs/user-flows.md, docs/operations.md, openapi.
