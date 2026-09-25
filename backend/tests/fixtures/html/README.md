# Fixture HTML trang khách sạn Booking.com (trang thật)

Các fixture ở đây là **HTML thật** bắt ngày 2026-09-25 qua proxy dân dụng Việt Nam, đúng đường đi
của worker (Playwright lấy cookie qua challenge → curl_cffi tải trang có ngày), rồi rút gọn chỉ còn
phần parser đọc (biến JS `b_hotel_id`/`b_hotel_name`/`b_csrf_token` với token đã thay bằng giá trị giả,
tiêu đề, ô `checkin`, thông báo hết phòng, bảng `#hprt-table`) và nén gzip.

| Fixture | Trang | Dùng để kiểm |
|---|---|---|
| `reverie_2026-10-10` | The Reverie Saigon, 1 đêm, 2 người lớn | 10 loại phòng (ô loại phòng là `<th rowspan>`), nhãn "We have N left" = dropdown, 1 loại phòng dropdown chạm trần 10, dòng giá "Only for 1 guest" bị lọc |
| `park-hyatt_2026-11-05` | Park Hyatt Saigon | 9 loại phòng, phòng không nhãn có dropdown < 10 |
| `jovia_sold_out_2026-10-03` | Jovia Hotel, ngày lịch báo hết phòng | `#no_availability_msg` → SOLD_OUT |
| `reverie_dates_dropped` | Trang Booking trả khi nghi bot (301 về URL trần) | `checkin` rỗng → không được coi là hết phòng |
| `reverie_2026-09-25_last_minute` | The Reverie, nhận phòng trong ngày | không có cột "Max persons" ("Sleeps: 2 adults" trong ô loại phòng), giá gạch, "Total cost to cancel", nhãn ở ô điều kiện |
| `rex_2026-09-25_partner_offers` | Rex Hotel | dòng "Booking Basic" (`bbasic`, giá đối tác) bị bỏ, ID loại phòng lấy từ dòng giá của khách sạn |
| `caravelle_2026-10-10` | Caravelle | nhóm chỉ có giá đối tác bị bỏ, 11 loại phòng |

Các số kỳ vọng viết tay trong `tests/unit/test_parser.py` được trích độc lập từ HTML (không qua
parser). File `*.expected.json` là golden sinh bằng `explore_fixture.py --emit-expected` từ chính
parser, chỉ để bắt hồi quy (không phải nguồn sự thật).

## Bắt trang mới / cập nhật khi Booking đổi giao diện

```bash
cd backend
uv run python scripts/capture_fixture.py https://www.booking.com/hotel/vn/<slug>.html 2026-10-10 1 <tên>
uv run python scripts/explore_fixture.py tests/fixtures/html/<tên>.html.gz          # đếm phần tử khớp từng selector
uv run python scripts/explore_fixture.py --emit-expected tests/fixtures/html/<tên>.html.gz
```

Nếu selector nào cho 0 kết quả, sửa hằng số trong `app/collector/booking/selectors.py`, tăng
`PARSER_VERSION`, cập nhật test rồi chạy `uv run sb reparse --since-days 30` để parse lại HTML thô.
Test live (`uv run pytest tests/live -m live`) gọi Booking thật, cần `PROXY_URL_TEMPLATE` thật.
