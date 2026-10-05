# Phase 4 — Adapter kênh (agent song song, mỗi kênh một thư mục riêng)
Mỗi kênh: `app/collector/<kênh>/` (urls.py thuần, client, parser, collector), fixture JSON/HTML thật trong `tests/fixtures/<kênh>/`, unit test parser + urls, báo cáo spike `reports/spike-<kênh>.md`.
- Agoda: suggest API, `room-grid`/`GetSecondaryData`, VND, giá gồm thuế + giá gốc + KM, `availableRooms`, "đặt N lần 24h".
- ivivu: `searchhotel` (định danh+toạ độ), token challenge → `HotelSearchReqContractAppV2`, supplier từng giá, `TopSale24hByHotel`, loại combo.
- Trip.com: suggest, room list API, "chỉ còn N phòng có giá này" (scope rate).
- Spike: Traveloka (headless bị chặn), Mytour (Tripi API), Expedia. Làm adapter nếu khả thi.
