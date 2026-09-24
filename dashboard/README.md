# Dashboard — Theo dõi đối thủ khách sạn

Ứng dụng Next.js (App Router, TypeScript, Tailwind) cho sản phẩm giám sát tình trạng phòng
và giá đối thủ trên Booking.com. Mọi dữ liệu lấy từ backend FastAPI (`backend/`) qua proxy
cùng origin `/api/...`, xác thực bằng cookie httpOnly `sb_session`.

## Chạy local

```bash
# backend chạy ở :8000 (xem Makefile ở gốc repo: `make api`)
cd dashboard
npm install
npm run dev          # http://localhost:3000
```

Trình duyệt gọi `http://localhost:3000/api/...`; Route Handler `src/app/api/[...path]/route.ts`
chuyển tiếp tới `API_INTERNAL_URL` (mặc định `http://localhost:8000`). Không cần cấu hình CORS
vì cookie đi cùng origin.

## Scripts

| Lệnh | Việc làm |
|---|---|
| `npm run dev` | dev server |
| `npm run build` | build production (`output: "standalone"`) |
| `npm run start` | chạy bản build |
| `npm run lint` | ESLint (eslint-config-next, gồm rule React Compiler) |
| `npm run typecheck` | `next typegen` rồi `tsc --noEmit` |
| `npm run gen:api` | sinh `src/lib/api-types.ts` từ `../docs/api/openapi.json` (commit file sinh ra) |

Khi backend đổi API: cập nhật `docs/api/openapi.json`, chạy `npm run gen:api`, sửa
`src/lib/api.ts` nếu cần.

## Biến môi trường

| Biến | Lúc nào | Ý nghĩa |
|---|---|---|
| `API_INTERNAL_URL` | runtime | URL backend mà server Next.js gọi tới, đọc ở mỗi request (trong Docker Compose: `http://api:8000`). |
| `NEXT_PUBLIC_API_URL` | build arg | Nhận để tương thích `infra/docker-compose.yml`; hiện không dùng vì trình duyệt luôn gọi cùng origin. |
| `PORT`, `HOSTNAME` | runtime | Cổng/host của `server.js` (mặc định 3000 / 0.0.0.0 trong Dockerfile). |

## Docker

`Dockerfile` nhiều tầng: `npm ci` → `next build` → tầng chạy chỉ chứa `.next/standalone`,
`.next/static`, `public`, chạy `node server.js` với user không phải root.

Lưu ý: `rewrites()` trong `next.config` được serialize lúc build nên không thể đọc env lúc
chạy. Vì vậy proxy API làm bằng Route Handler; chỉ cần đặt `API_INTERNAL_URL` trong
`environment:` của compose, không cần build lại.

## Kiến trúc

```
src/
  proxy.ts                      # (Next 16: thay middleware.ts) chuyển về /login khi thiếu cookie
  app/api/[...path]/route.ts    # proxy /api/* -> API_INTERNAL_URL/*
  lib/api-types.ts              # sinh từ OpenAPI
  lib/api.ts                    # client có kiểu: ApiError, 401 -> /login, tự gắn tenant_id cho operator
  lib/session.tsx               # SessionProvider: /auth/me, danh sách tenant, tenant đang chọn (localStorage)
  lib/hooks.ts                  # useApi (tải + reload), useInterval, useMutation
  lib/format.ts                 # Intl vi-VN: tiền, ngày, phần trăm; Decimal-chuỗi -> số
  lib/labels.ts                 # nhãn tiếng Việt cho mã trạng thái
  components/                   # ui kit nhỏ, app shell + tenant switcher, line chart SVG, bảng sự kiện
  app/(app)/...                 # các màn hình (client-side fetching)
```

Phân quyền phía giao diện:
- `operator`: thấy bộ chuyển tenant ở thanh trên và mục Vận hành (`/admin/*`); mọi request
  theo tenant tự kèm `?tenant_id=`.
- `tenant_admin`: đọc/ghi tenant của mình.
- `viewer`: chỉ đọc, các nút ghi bị ẩn. Người dùng tenant vào `/admin/*` bị chuyển về `/overview`.

## Màn hình

| Đường dẫn | Nội dung |
|---|---|
| `/login` | Đăng nhập |
| `/overview` | Heatmap khách sạn × ngày (khách sạn của bạn trên cùng), dải compset, đợt quét gần nhất, chọn khoảng ngày |
| `/hotels/[id]` | Chỉ số theo ngày và dòng thời gian sự kiện của một khách sạn |
| `/hotels/[id]/dates/[date]` | Từng loại phòng ở lần quét gần nhất, biểu đồ rooms_left và giá theo thời gian, quan sát, sự kiện |
| `/insights`, `/insights/[id]` | Bản tin AI: danh sách, tạo theo yêu cầu (poll 5s), chi tiết với bằng chứng bấm được, mục bị loại |
| `/events` | Sự kiện có lọc theo khách sạn, loại, ngày lưu trú, thời điểm quan sát; phân trang; `?highlight=<id>` |
| `/settings` | Watchlist, lịch quét, người dùng, nhập PMS (template, xem trước, ánh xạ cột, lỗi từng dòng, lịch sử) |
| `/admin/tenants` | Operator: tạo/sửa tenant, chọn tenant để xem |
| `/admin/users` | Operator: mọi tài khoản, tạo, khoá/mở, đặt lại mật khẩu |
| `/admin/health` | Operator: block rate, đợt quét, session, liên kết Grafana; tự làm mới 30s |
