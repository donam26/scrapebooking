# Fixture HTML trang khách sạn Booking.com

Ba fixture ở đây (`available_with_badge`, `available_no_badge`, `sold_out`) là **trang mô phỏng**
dựng tay theo cấu trúc bảng phòng `#hprt-table` mà Booking dùng nhiều năm, vì môi trường
dựng code ban đầu không có residential proxy để bắt trang thật.

Trước khi chạy thật (Task 10, Step 7–9 trong kế hoạch giai đoạn 1) **bắt buộc** thay bằng
trang thật:

```bash
cd backend
uv run python scripts/capture_fixture.py https://www.booking.com/hotel/vn/<slug>.html 2026-10-10 1 available_no_badge
uv run python scripts/capture_fixture.py https://www.booking.com/hotel/vn/<slug>.html 2026-10-03 1 available_with_badge
uv run python scripts/capture_fixture.py https://www.booking.com/hotel/vn/<slug>.html 2026-12-31 1 sold_out
for f in available_with_badge available_no_badge sold_out; do
  uv run python scripts/explore_fixture.py tests/fixtures/html/$f.html
done
```

Nếu selector nào cho 0 kết quả, sửa hằng số trong `app/collector/booking/selectors.py`
(không sửa parser), rồi emit lại golden:

```bash
for f in available_with_badge available_no_badge sold_out; do
  uv run python scripts/explore_fixture.py --emit-expected tests/fixtures/html/$f.html
done
```

Test `tests/unit/test_parser.py::test_rate_plan_grouping_by_room_type` kiểm tra giá trị cụ thể
của fixture mô phỏng; khi thay bằng trang thật, cập nhật các giá trị trong test đó theo trang.
