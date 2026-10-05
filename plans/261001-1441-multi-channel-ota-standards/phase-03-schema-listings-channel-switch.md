# Phase 3 — Schema 0007 + chuyển backend
Migration `0007_multi_channel`:
- `listings(id, hotel_id, channel, listing_key, external_id, url, name, status, match_score, last_error, verified_at, created_at)`; UNIQUE(hotel_id, channel), UNIQUE(channel, listing_key). Backfill từ `hotels.booking_*` (status active).
- `hotels`: thêm `address, lat, lng`; bỏ `booking_url, booking_slug, booking_hotel_id`.
- `channel` (mặc định 'booking') ở `scan_runs, probes, room_types, room_snapshots, hotel_date_snapshots, hotel_date_metrics, availability_events`; `room_types.booking_room_id` → `external_room_id`, UNIQUE(hotel_id, channel, external_room_id); PK `hotel_date_metrics` → (hotel_id, channel, stay_date); `room_snapshots.stock_scope`.
- `listing_demand_signals(id, hotel_id, channel, scan_run_id, stay_date?, kind, value, window_hours, raw_text, observed_at)`.
- `tenants.reference_channel` ('booking'); horizon mặc định 90 (tenant đang 30 → 90).
Code: scheduler/scan_now (run theo kênh), worker, snapshots repo, analytics (lọc kênh), compset (theo kênh), data router (`?channel=`), watchlist, notify, insight, export, cli, schemas, tests.
