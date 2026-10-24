# Chạy thật 16/10/2026: thị trường theo quận/bán kính + thang phòng trống

Proxy mới `14.224.225.153:24767` (IP ra 171.236.164.217, VN). API + 2 worker Booking + worker jobs
chạy trên máy (Redis db 1), DB dev đã lên 0018. Tenant 9 (Rex Hotel Saigon).

## Khu vực
| # | Khu vực | Kiểu | Phân khúc | KS đã biết |
|---|---|---|---|---|
| 1 | Quận 1 (Booking) | district 2088 | khách sạn + resort + căn hộ KS | 584 |
| 2 | 3 km quanh Rex | latlong (10.77574, 106.70141) + 3000 m | như trên | 856 |

Không bị chặn lần nào (~1.100 request thị trường + 450 probe compset, 442 ok).

## Chi phí mỗi đêm
| Khu vực | Đêm | Request TB (min–max) | Giây TB | Tổng request |
|---|---|---|---|---|
| Quận 1 | 3 | 34 (30–41) | 88 | 102 |
| 3 km quanh Rex | 14 | 43 (36–51) | 113 | 604 |

(Lượt này còn nấc 2 và lấp-theo-giá cũ; mặc định mới bỏ nấc 2 và chỉ lấp khi thiếu > 2% → ~5–11
request ít hơn mỗi đêm.) So với quét chi tiết top 300 KS × ~30 đêm ≈ 9.000 trang/ngày.

## 3 km quanh Rex, 14 đêm (phân khúc khách sạn + resort + căn hộ KS; mẫu số 831)
| Đêm | Còn phòng | Hết phòng ≥ | ≥10 phòng | ≥30 phòng | Mức căng c10/c1 | Phòng còn bán ≥ | Giá trung vị |
|---|---|---|---|---|---|---|---|
| T6 16/10 | 604 | 27% | 340 | 139 | 0,56 | 7.848 | 1,05tr |
| T7 17/10 | 638 | 23% | 404 | 184 | 0,63 | 9.432 | 1,13tr |
| CN 18/10 | 786 | 5% | 579 | 267 | 0,74 | 13.237 | 0,96tr |
| T2 19/10 | 822 | 1% | 636 | 316 | 0,77 | 14.749 | 0,96tr |
| T3 20/10 | 819 | 1% | 645 | 322 | 0,79 | 14.943 | 0,96tr |
| T4 21/10 | 824 | 1% | 649 | 325 | 0,79 | 15.083 | 0,92tr |
| T5 22/10 | 810 | 3% | 641 | 307 | 0,79 | 14.609 | 0,95tr |
| T6 23/10 | 813 | 2% | 616 | 295 | 0,76 | 14.023 | 1,02tr |
| T7 24/10 | 785 | 6% | 603 | 295 | 0,77 | 13.868 | 1,04tr |
| CN 25/10 | 816 | 2% | 639 | 338 | 0,78 | 15.087 | 0,96tr |
| T2 26/10 | 825 | 1% | 667 | 351 | 0,81 | 15.514 | 0,96tr |
| T3 27/10 | 831 | 0% | 688 | 363 | 0,83 | 15.993 | 0,98tr |
| T4 28/10 | 829 | 0% | 682 | 353 | 0,82 | 15.669 | 0,96tr |
| T5 29/10 | 827 | 0% | 685 | 356 | 0,83 | 15.796 | 0,97tr |

Đọc: đêm nay và T7 căng rõ (thang tụt mạnh dù "còn phòng" chỉ giảm 25%); hai cuối tuần sau
căng nhẹ (T7 24/10: ≥10 phòng 603 so với ~640–690 ngày thường) và giá trung vị nhích lên.
Rex: còn 60–79 phòng đêm nay (quét trang), giá 3,9tr — đắt hơn 92% KS khu vực.

## Đối chiếu thang tìm kiếm với thang lịch (`scripts/validate_market_ladder.py 1`)
Compset 5 KS × 3 đêm (16–18/10), lượt quét compset 194 cùng giờ: **khớp 15/15**.

| KS | Đêm | Tìm kiếm | Lịch | Trang |
|---|---|---|---|---|
| Reverie | 16/10 | ≥30 | 40–49 | 40–49 |
| Reverie | 17/10 | 10–19 | 15–19 | 15–19 |
| Reverie | 18/10 | 5–9 | 5–9 | 5–9 |
| Meander | 16/10 | 10–19 | 1–14 | 10–14 |
| Meander | 17/10 | 20–29 | 25–29 | 25–29 |
| Rex | 16/10 | ≥30 | 60–79 | 60–79 |
| Caravelle | 16–18/10 | ≥30 | ≥100 | ≥100 |
| Park Hyatt | 16–18/10 | ≥30 | ≥40 / ≥1 | ≥40–46 |

⇒ Khoảng phòng còn từ thang tìm kiếm đúng ở mọi cặp đo được, chỉ thô hơn (trần 30, bậc 3/5/10/20/30).
Mới 3 đêm × 5 KS; cần ~2 tuần dữ liệu trước khi bỏ quét chi tiết top N.

## Review độc lập (code-reviewer) — đã sửa
- H: thang thiếu nấc khi hết trần → đếm trang đầu mọi nấc ngay sau trang danh sách đầu, chỉ lưu thang
  khi đủ nấc, điền 0 trên nấc 0; `enumerated` chỉ khi danh sách + mọi nấc đủ ≥ 98% và ≤ 1.000.
- H: cột `nflt` thêm vào 0018 sau khi đã chạy → ALTER tay trên DB dev + test.
- M: 4xx đầu vào/5xx không còn bị coi là chặn (không tạm dừng kênh); 200 không phải JSON hoặc thiếu
  csrf = chặn (thu hồi session); lỗi GraphQL hỏi lại 1 lần trước khi dự phòng SSR.
- M: thẻ "nới thêm" không còn lọt qua dự phòng HTML / tổng dự phòng / facet hạng sao.
- M: đổi phân khúc/bán kính → ẩn lượt quét phạm vi cũ, dựng lại danh sách KS khu vực.
- L: khoảng phòng theo nấc của chính lượt quét; allow-list trường phân khúc; log sai tiền tệ.

Vòng review 2 (kiểm lại): High đã hết. Sửa thêm 3 Medium: thứ tự chọn lượt quét dùng CASE (NULL
không đứng đầu khi DESC; ưu tiên lượt có thang, nguồn GraphQL); vòng lật trang chặn bởi trần 1.000 thay
vì số trong khu vực (kết quả nới thêm có thể xen giữa); điền `nflt` cho lượt cũ + chạy worker code mới.
Low: bị chặn đúng lúc hết trần → "capped" (không tạm dừng cả kênh khi chưa thử lại được).

Quét lại Quận 1 bằng code mới (bỏ nấc 2, lấp theo giá chỉ khi thiếu > 2%): 20–34 request/đêm (trước
30–41), độ phủ 98–100%, `enumerated` đủ.

## Sự cố trong lúc chạy
Khởi động lại worker bằng `env $ENVV …` (zsh không tách chuỗi) → worker trỏ nhầm Redis 6379/0 (Redis
riêng của máy) ~1 phút; chỉ một khoá `arq:in-progress:cron:…` bị tạo, đã xoá; chạy lại với `export`.

## Câu hỏi mở
1. Khi nào bỏ quét chi tiết top N (`detail_max_hotels`) — đợi 2 tuần đối chiếu?
2. Có chạy lại cả stack Docker (scheduler 03:00 hằng ngày) với image mới không — hiện chỉ chạy tay trên máy.
3. KS "của mình" ở Vũng Tàu để tạo khu vực Bãi Sau/bán kính.
