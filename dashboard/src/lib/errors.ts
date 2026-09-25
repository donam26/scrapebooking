/**
 * Dịch thông báo lỗi của backend (giữ tiếng Anh ổn định cho API/log/test) sang tiếng Việt
 * khi hiển thị. Chuỗi không khớp quy tắc nào được giữ nguyên.
 */

const FIELD_LABEL: Record<string, string> = {
  email: "Email",
  password: "Mật khẩu",
  role: "Vai trò",
  name: "Tên",
  timezone: "Múi giờ",
  scan_times: "Giờ quét",
  horizon_days: "Horizon",
  insight_hour: "Giờ tạo bản tin",
  insight_language: "Ngôn ngữ bản tin",
  country_code: "Mã nước",
  booking_url: "URL Booking.com",
  label: "Nhãn",
  stay_date: "Ngày lưu trú",
  rooms_total: "Tổng phòng",
  rooms_sold: "Phòng đã bán",
  rooms_available: "Phòng còn",
  occupancy_pct: "Công suất",
  adr: "ADR",
  revenue: "Doanh thu",
  start: "Từ ngày",
  end: "Đến ngày",
};

type Rule = [RegExp, (m: RegExpMatchArray) => string];

const RULES: Rule[] = [
  // xác thực, phân quyền
  [/^invalid credentials$/, () => "Email hoặc mật khẩu không đúng"],
  [/^(not authenticated|invalid session)$/, () => "Phiên đăng nhập hết hạn, vui lòng đăng nhập lại"],
  [/^user disabled$/, () => "Tài khoản đã bị khoá"],
  [/^operator only$/, () => "Chỉ tài khoản vận hành được thực hiện thao tác này"],
  [/^read-only role$/, () => "Tài khoản chỉ xem không được thay đổi dữ liệu"],
  [/^cannot access another tenant$/, () => "Không có quyền xem dữ liệu của tenant khác"],
  [/^user has no tenant$/, () => "Tài khoản chưa được gán tenant"],
  [/^tenant_id is required for operator$/, () => "Hãy chọn tenant ở thanh trên"],
  [/^tenant_id required$/, () => "Hãy chọn tenant cho người dùng"],
  // người dùng
  [/^email already exists$/, () => "Email đã được dùng cho tài khoản khác"],
  [/^user not found$/, () => "Không tìm thấy người dùng"],
  [/^cannot lock or change the role of your own account$/, () => "Không thể tự khoá hoặc tự đổi vai trò tài khoản đang đăng nhập"],
  [/^cannot remove the last active operator$/, () => "Không thể khoá hoặc hạ vai trò operator đang hoạt động cuối cùng"],
  // tenant, lịch quét
  [/^tenant not found$/, () => "Không tìm thấy tenant"],
  [/^unknown timezone '(.+)'.*$/, (m) => `Múi giờ không hợp lệ: ${m[1]} (ví dụ đúng: Asia/Ho_Chi_Minh)`],
  [/^bad time '(.+)'$/, (m) => `Giờ không hợp lệ: ${m[1]} (định dạng HH:MM)`],
  [/^scan_times must not be empty$/, () => "Cần ít nhất một giờ quét"],
  [/^at most (\d+) scan_times per day$/, (m) => `Tối đa ${m[1]} mốc giờ quét mỗi ngày`],
  // watchlist, quét
  [/^not a booking\.com url: (.*)$/, () => "URL không phải của Booking.com"],
  [/^not a hotel page url: (.*)$/, () => "URL không phải trang khách sạn Booking.com (dạng https://www.booking.com/hotel/vn/ten-khach-san.html)"],
  [/^hotel not in watchlist$/, () => "Khách sạn không có trong watchlist"],
  [/^hotel not found$/, () => "Không tìm thấy khách sạn"],
  [/^watchlist is empty$/, () => "Watchlist trống: thêm khách sạn trước"],
  [/^job queue unavailable$/, () => "Hàng đợi xử lý không sẵn sàng, thử lại sau"],
  [/^scan run already created$/, () => "Đợt quét vừa được tạo, thử lại sau vài giây"],
  // dữ liệu
  [/^end before start$/, () => "Ngày kết thúc trước ngày bắt đầu"],
  [/^range over (\d+) days$/, (m) => `Khoảng ngày tối đa ${m[1]} ngày`],
  // bản tin
  [/^insight not found$/, () => "Không tìm thấy bản tin"],
  [/^no scan data yet.*$/, () => "Chưa có dữ liệu quét/analytics cho kỳ này"],
  [/^no json output$/, () => "Mô hình không trả về kết quả hợp lệ"],
  [/^schema: (.*)$/, (m) => `Kết quả mô hình sai cấu trúc: ${m[1]}`],
  [/^timeout: .*$/, () => "Quá thời gian: bộ xử lý nền không phản hồi trong 10 phút"],
  // PMS
  [/^PMS data only for role=self hotel$/, () => "Chỉ nhập PMS cho khách sạn vai trò “Khách sạn của bạn”"],
  [/^unknown columns (.*)$/, (m) => `Cột không hợp lệ: ${m[1]}`],
  [/^unknown adapter '(.+)'$/, (m) => `Nguồn dữ liệu không hỗ trợ: ${m[1]}`],
  [/^cannot decode file$/, () => "Không đọc được mã hoá ký tự của tệp"],
  [/^empty file or missing header row$/, () => "Tệp rỗng hoặc thiếu dòng tiêu đề"],
  [/^empty sheet$/, () => "Sheet đầu tiên của tệp Excel trống"],
  [/^cannot read excel: .*$/, () => "Không đọc được tệp Excel"],
  [/^missing mapping for (\w+)$/, (m) => `Chưa chọn cột cho ${FIELD_LABEL[m[1]] ?? m[1]}`],
  [/^unrecognised date '?(.*?)'?$/, (m) => `Ngày không hợp lệ: ${m[1]}`],
  [/^duplicate date (.+)$/, (m) => `Trùng ngày ${m[1]}`],
  [/^not a number "?'?(.*?)'?"?$/, (m) => `Không phải số: ${m[1]}`],
  [/^not an integer "?'?(.*?)'?"?$/, (m) => `Không phải số nguyên: ${m[1]}`],
  [/^sold (\d+) > total (\d+)$/, (m) => `Phòng đã bán (${m[1]}) lớn hơn tổng phòng (${m[2]})`],
  [/^out of range (.+)$/, (m) => `Công suất ${m[1]}% nằm ngoài 0–100`],
  // lỗi kiểm tra dữ liệu của FastAPI/pydantic
  [/^Field required$/, () => "bắt buộc nhập"],
  [/^String should have at least (\d+) characters?$/, (m) => `cần ít nhất ${m[1]} ký tự`],
  [/^String should have at most (\d+) characters?$/, (m) => `tối đa ${m[1]} ký tự`],
  [/^Input should be greater than or equal to (.+)$/, (m) => `phải ≥ ${m[1]}`],
  [/^Input should be less than or equal to (.+)$/, (m) => `phải ≤ ${m[1]}`],
  [/^value is not a valid email address.*$/, () => "email không hợp lệ"],
  [/^String should match pattern .*$/, () => "giá trị không hợp lệ"],
];

export function translateError(message: string): string {
  const text = message.trim();
  for (const [re, fn] of RULES) {
    const m = text.match(re);
    if (m) return fn(m);
  }
  return message;
}

/** Tên trường của lỗi validation (`loc`) sang nhãn tiếng Việt. */
export function fieldLabel(name: string): string {
  return FIELD_LABEL[name] ?? name;
}
