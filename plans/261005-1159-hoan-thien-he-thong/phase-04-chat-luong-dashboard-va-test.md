# Phase 4: Chất lượng dashboard và test

Ước lượng: 1 tuần. Phụ thuộc: phase 0 (CI). Chạy song song với phase 2 được (ranh giới: phase 4 chỉ sửa
`dashboard/` và `backend/tests/`). Trạng thái: todo.

## Mục tiêu
Dashboard có test tự động, data layer có cache/dedupe, múi giờ nhất quán theo tenant, không render nặng, file
< 400 dòng; backend có contract test cho kênh và test cho module đang 0 test.

## Việc

### 4.1 Harness test FE
- Vitest + React Testing Library: `dashboard/vitest.config.ts`, `src/test-utils.tsx` (NextIntl provider + session mock).
- Unit: `lib/format.ts` (tiền, ngày theo tz), `lib/errors.ts` (rule → khoá), `lib/market-metrics.ts`, `lib/night-reason.ts`,
  `lib/channels.ts`, `components/date-range.tsx`.
- Component: `Board` (render 5 KS × 14 đêm, hover không re-render thẻ khác – đo bằng `React.Profiler`), `heatmap-table`,
  `insight-view` (bằng chứng click), `watchlist-tab` (thêm URL → chip kênh), `pms-tab` (preview → ánh xạ → import).
- Playwright e2e smoke trong CI chạy trên compose (api + seed_demo + dashboard): login → dashboard → competitors →
  availability → settings watchlist thêm URL → events CSV → admin health. Ảnh chụp desktop + mobile làm baseline.
- CI dashboard job: `npm test`, `npx playwright test` (job riêng, cần docker).

### 4.2 Data layer
- Thay `useApi` bằng TanStack Query (hoặc SWR): `queryKey=[path, tenantId, locale]`, `staleTime` 30 s, dedupe `/settings`
  (3 → 1), `refetchIntervalInBackground=false`, `AbortSignal`, reset cache khi đổi tenant (`queryClient.clear()`),
  retry 1 lần cho GET.
- `lib/api.ts`: dùng kiểu `paths` từ `api-types.ts` cho đường dẫn (openapi-fetch) để đổi route là lỗi tsc; bỏ 2 kiểu
  inline (`:225`, `:293`); tenant đang chọn qua context thay biến module.
- Terminal+: dùng endpoint gộp demand-signals (phase 3.3), bỏ N+1; bản tin chi tiết dùng `GET /events/{id}`.
- Poll bản tin: list và detail cùng coi `pending|batch_pending` (hoặc bỏ `batch_pending` sau phase 1.5) qua một hook
  `useInsightPolling`.

### 4.3 Múi giờ
- `useDateRange`, `today/page.tsx`, `fmtWhen/fmtDateTime/fmtTime` nhận `timeZone` từ `useTenantToday`/settings;
  `i18n/request.ts` `timeZone` đặt theo tenant (đọc từ cookie/tenant settings) thay cứng `Asia/Ho_Chi_Minh`.
- Test: operator ở `America/Los_Angeles` thấy "đêm nay" đúng ngày VN.

### 4.4 Hiệu năng render và cấu trúc
- `Board`: hover state đưa xuống từng thẻ (hoặc CSS `:hover` + `data-night`), `ctx` trong `useMemo`, `React.memo` cho
  `HotelCard`/`NightCell`; heatmap: build `Map<string, Cell>` một lần; bảng lịch sử >200 dòng dùng `react-virtual`.
- Tách file: `board.tsx` → `components/board/{board,strip,hotel-card,night-cell}.tsx` (chuyển ra khỏi `overview/`);
  `ui.tsx` → `components/ui/{button,field,panel,tabs,segmented,popover}.tsx`; `hotels/[id]/dates/[date]/page.tsx` →
  `room-rates-table`, `channel-compare`, `history-charts`, `observation-log`; `watchlist-tab` → `listing-row`,
  `add-hotel-form`, `suggestion-chip`; `pms-tab` → `mapping-editor`, `import-result`.
- Gộp trùng: `lib/url-params.ts` (1 helper thay 5), `lib/market-mood.ts`, `components/stat-box.tsx`, `lib/city-fallback.ts`;
  chọn một hệ chart (recharts) và xoá SVG tay nếu không có lý do.
- Hex rời (123 chỗ) → token `--sb-*` trong `globals.css`; `"VND"` từ `settings.currency`; `"Booking.com"` từ
  `labels.channel`.
- `notFound()` cho id/date không hợp lệ; confirm khi tạm dừng/xoá khách sạn và "Quét tất cả"; arrow-key cho
  `Segmented`/`Tabs`; chuông: refetch 5 phút + "mới" theo `last_seen_at` lưu localStorage; `/runs` phân trang; users-tab
  lọc theo tenant ở API (`GET /users?tenant_id`); quyết định bỏ `/today` hoặc biến thành chế độ mobile của `/dashboard`.
- Màn `/forgot`, `/reset` cho password reset (API ở phase 2.1).

### 4.5 Backend test bổ sung
- Contract test kênh: `tests/unit/test_channel_contract.py` chạy `build(deps giả)` cho mọi `ChannelCode` collectable, kiểm
  5 method + `PARSER_VERSION`; `fake.py` triển khai đủ `ChannelCollector`.
- `test_budget.py` (Redis giả/fakeredis), `test_token_minter_allowed.py`, Booking `verify/suggest/search_page` với HTML
  fixture, Trip.com `verify/suggest`, Mytour nhánh partial, proxy xoay nhiều template, `classify_response` với JSON
  chứa "access denied" (không block), `test_seed_demo`.
- Analytics: currency lệch, UTC off-by-one, `channel_closed` không lặp 24 h, giữ giá khi blocked (phase 1 viết chung).
- Scheduler: 2 scheduler song song (advisory lock), run hết hạn khi worker còn ghi, pause → catch-up.
- Mục tiêu coverage backend ≥ 80% dòng cho `app/` (đo bằng `pytest --cov`, bật báo cáo trong CI, chưa gate).

## Tiêu chí nghiệm thu
- CI có 3 job xanh: backend, dashboard (lint/type/build/i18n/vitest), e2e (playwright smoke).
- Mở `/dashboard`: đúng 1 request `/settings`; hover 1 ô heatmap không re-render thẻ khác (Profiler test).
- Không file `.tsx` > 400 dòng; `grep -c "#[0-9a-f]\{6\}" src --include=*.tsx` ngoài marketing = 0.
- Operator tz khác VN thấy đúng "đêm nay" (test).
- Contract test pass cho 5 kênh; `budget.py`, `token_minter.py` có test.

## Rủi ro
- Thay data layer chạm mọi trang: làm theo trang, giữ `useApi` adapter mỏng bọc React Query để migrate dần.
