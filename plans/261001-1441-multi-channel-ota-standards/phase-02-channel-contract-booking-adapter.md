# Phase 2 — Hợp đồng kênh
- `app/channels/registry.py`: `ChannelCode`, tên hiển thị, host, `parse_listing_url(url) -> ListingUrl` (thuần, API import được).
- `app/domain/models.py`: `HotelRef` → `ListingRef(hotel_id, channel, listing_key, external_id, url, country_code)`; `RoomOffer.external_room_id`, `stock_scope`; `RatePlan.price_original/taxes_included/promo_label/source_supplier`; `ProbeResult.external_id`, `demand_signals`; `DemandSignal`, `ListingIdentity`, `ListingCandidate`.
- `Collector` Protocol thêm `verify`, `suggest`.
- Booking: `app/collector/booking/urls.py` có `parse_url`; collector đọc `ListingRef`.
