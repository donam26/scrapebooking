# Song ngữ vi/en toàn hệ thống

Quyết định (người dùng chọn 2026-10-02): toàn hệ thống (web + text API + email/CSV/bản tin); chọn
ngôn ngữ bằng cookie, URL giữ nguyên. Chuẩn: `docs/i18n.md`.

| Phase | Nội dung | Owner | Trạng thái |
|---|---|---|---|
| 1 | Nền FE: next-intl, i18n/, messages/, format/labels/errors/hooks, root layout, manifest, proxy Accept-Language, LocaleSwitcher, app-shell, i18n-check | main | xong |
| 2a | FE dùng chung: components/*, lib helpers → `components`, `helpers` | agent shared | xong |
| 2b | Landing + login → `landing`, `auth` | agent landing | xong |
| 2c | Backend: app/i18n, text API, CSV, email, ngày lễ, bản tin | agent backend | xong |
| 3 | Trang app (chạy sau 2a): dashboard/today/overview/terminal; availability/rates/pace/competitors/market; hotels/events/insights; settings; admin/runs | 5 agent | xong |
| 4 | Kiểm tra: typecheck, lint, build, i18n:check, pytest, screenshot vi/en | main + reviewer | xong (review: 7 lỗi đã sửa) |

Ownership: mỗi agent chỉ sửa tệp và namespace JSON của mình. `common/format/labels/errors/shell`
chỉ main sửa.

Kết quả 2026-10-02: 1793 khoá × 2 ngôn ngữ, i18n:check 0 lỗi; tsc/eslint/build sạch; backend 509 unit + integration pass. Báo cáo trong reports/.
Còn lại: rebuild image Docker (api/dashboard) khi deploy; email còn thương hiệu "ScrapeBooking"; text cào từ kênh (tên gói giá, raw_text tín hiệu cầu) vẫn là dữ liệu tiếng Việt.
