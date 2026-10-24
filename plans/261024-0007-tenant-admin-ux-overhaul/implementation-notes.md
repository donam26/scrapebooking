# Ghi chú triển khai (chung cho mọi phần việc)

Cập nhật: 24/10. Đọc kèm `plan.md` (quyết định Q1–Q9, cấu trúc điều hướng) và ba file phase.

## Đã xong (đợt 1, frontend)
- **Khung app** (`dashboard/src/components/app-shell.tsx`).
  - 5 tab: Hôm nay `/today` · Lịch giá & phòng `/calendar` · Đối thủ `/competitors` · Thị trường `/market` · Báo cáo `/insights`. Mỗi tab có `match` gồm cả URL cũ.
  - Mobile <768px dùng thanh đáy. Cài đặt là nút ⚙ trên thanh trên.
  - Pill độ mới dữ liệu mở bảng "Tình trạng dữ liệu" (câu trạng thái, 7 ngày, cách đọc số, link `/runs`). Menu ⓘ đã bỏ.
  - Chuỗi ở `messages/*/shell.json` (`nav`, `navShort`, `freshness`).
- **Hôm nay** (`app/(app)/today/*`): việc cần làm (`components/today-actions.tsx`), dải 14 đêm (`night-strip.tsx`), thay đổi 24 giờ, bản tin, thẻ "Khách sạn của bạn đêm nay". `/dashboard` chuyển về `/today`. Namespace `dashboard` đã xoá.
- **Thẻ gợi ý** (`components/market-suggestion.tsx`):
  - props `brief` (một câu lý do + "Cách tính") và `staleSince` (mờ, khoá nút);
  - nhãn "Tôi đã đổi giá";
  - ô giá có dấu ngăn nghìn;
  - đã ghi thì thu một dòng có "Hoàn tác".
  - Helper trong `lib/market.ts`: `mainReason(s)`, `useMarketText().suggestionBadge(s)` (nhãn "Giá thấp hơn mức thường" khi có lý do `below_usual`).
- **Dữ liệu cũ:**
  - `.sb-stale` (globals.css) không còn làm xám/mờ: giữ màu nhiệt, sọc chéo ở góc phải.
  - `--sb-faint` = #6b7280 (đạt 4,5:1).
  - Helper `lastPrice(cell)` trong `lib/market-metrics.ts` trả `{value, stale}`: luôn hiện giá cuối đọc được kèm dấu cũ (chữ `text-muted`, `title` giải thích) thay vì "—". `bookablePrice()` giữ nguyên cho các phép tính (trung vị, hạng).
- `login`, `manifest.start_url`, logo, not-found và error đều trỏ về `/today`.

## Quy ước bắt buộc
- **Chữ hiển thị:** không viết cứng. Thêm khoá ở cả `messages/vi/<ns>.json` và `messages/en/<ns>.json`, dùng `useTranslations`. Chạy `cd dashboard && npm run i18n:check`. Namespace mới thì thêm vào `messages/{vi,en}/index.ts`.
- **File JSON dùng chung** (`components.json`, `helpers.json`, `labels.json`, `common.json`): chỉ sửa bằng Edit nhỏ, thay đúng một đoạn duy nhất, không Write cả file. Agent khác có thể đang sửa phần khác của cùng file.
- **Từ ngữ** (L1, áp cho mọi chuỗi vi mới hoặc sửa):

  | Không dùng | Dùng |
  |---|---|
  | compset | nhóm đối thủ |
  | trung vị | giá giữa (của đối thủ); ⓘ giải thích "một nửa rẻ hơn, một nửa đắt hơn" |
  | ≥N / cận dưới / mức sàn | còn ít nhất N |
  | OTB | phòng đã đặt (PMS) |
  | pickup | đặt thêm |
  | pace | nhịp đặt phòng |
  | định vị | vị trí giá |
  | chuẩn CoStar STR | nhóm đối thủ có cân không |

  Tenant không thấy tên biến môi trường, mã lượt quét `#id`, "request", "probe", "job".
- **Giá:** giá niêm yết ≠ ADR. Chỉ báo lấp đầy luôn có "≈" và không gọi là công suất. Không bịa số. VND.
- **Tuổi dữ liệu:** mọi màn có số Booking hiện `DataUpdated` (`components/freshness.tsx`) trong `PageStrip`. Giá cũ dùng `lastPrice` như trên. Trạng thái rỗng phải nói vì sao trống. Khi `useDataFreshness().stale` thì nói "chưa có lượt quét mới", không đổ lỗi cho bộ lọc.
- **Mobile 375px:** trang không cuộn ngang (`document.documentElement.scrollWidth - innerWidth == 0`). Bảng hoặc lưới rộng cuộn trong khung riêng (`sb-scroll overflow-x-auto`), dùng `min-w-0` và `flex-wrap`.
- **Mặc định kỳ xem:** 14 đêm ở mọi màn (`DateRangePicker defaultDays={14}`).
- **Design:** DESIGN.md mục "App OTARadar". Thẻ `Card`, `PageStrip`, `KpiCard`, `Note`, `EmptyState` có sẵn trong `components/`. Không tạo bản "enhanced" của file. Sửa thẳng file hiện có.

## Môi trường thử
- **Dev API** :8001 tự nạp lại khi sửa `backend/app`. Chạy trên DB **bản sao** `scrapebooking_ux` (dữ liệu thật tenant 9 sao ra, có vài thao tác thử của audit). Redis db 2, không có worker.
- **Dashboard dev** :3100 (Next dev, HMR). Không khởi động server thứ hai trong `dashboard/`.
- **Đăng nhập:** cookie `sb_session` lấy từ `/private/tmp/claude-501/-Users-hnam--claude-spares-spare-jj0qEN/37328e95-aa5c-4754-a0f1-298abbb0a22e/scratchpad/token2.txt` (tenant_admin, tenant 9). Thêm cookie `NEXT_LOCALE=vi|en`.
- **Chụp và đo:** `backend/.venv/bin/python <scratchpad>/shoot.py <out_dir> <slug…>`, env `SB_TOKEN=$(cat <scratchpad>/token2.txt)`, tuỳ chọn `LOCALES=vi VIEWS=desktop,mobile`. Danh sách route nằm trong `ROUTES` của script; có thể chép script ra bản riêng để thêm route mới. Kết quả ghi `_shots.json` (overflow_px, lỗi console, request lỗi).
- **Kiểm tra:** `cd dashboard && npm run typecheck && npm run lint && npm run i18n:check`.
- Không chạy pytest khi chưa được giao (chỉ một tiến trình pytest mỗi lúc). Không commit. Không đụng DB thật `scrapebooking`.
