# API phòng quản lý (`apps/manage_api`)

Tách biệt hoàn toàn với API phòng demo ([API_SPEC.md](API_SPEC.md)): cổng 8100, database `data/manage.db`, không dùng chung mã hay cấu hình.
OpenAPI sinh tự động tại `/docs` khi chạy. Tài liệu này ghi **vai trò được phép**, quy ước và các quy tắc nghiệp vụ.

## Quy ước chung

- **Xác thực:** cookie `sb_manage_session` (HttpOnly, SameSite=Lax; `Secure` khi `MANAGE_COOKIE_SECURE=true`), phiên hết hạn sau 12 giờ ở phía máy chủ.
  Mọi request **ghi** (`POST/PUT/PATCH/DELETE`) cần header `X-CSRF-Token` lấy từ `login`/`register`/`me`, và `Origin` (nếu có) phải thuộc danh sách cho phép.
- **Vai trò:** `platform_admin`, `owner`, `staff`, `customer`. Quyền kiểm tra ở backend trên từng endpoint. Thứ tự lỗi: chưa đăng nhập `401` → sai vai trò `403` → sai quán `404` (không lộ quán khác có tồn tại hay không).
- **Cô lập quán:** mọi đường `/api/venues/{venue_id}/...` chỉ cho người dùng thuộc đúng quán đó; admin nền tảng dùng nhóm `/api/admin`.
- **Thời gian/tiền:** UTC ISO 8601 (đuôi `Z`); VND số nguyên; **backend là nguồn thời gian, giá và tiền** (client không gửi giờ hay số tiền). "Ngày" của quán tính theo `MANAGE_TIMEZONE` (mặc định `Asia/Ho_Chi_Minh`).
- **Idempotency:** `open` (409 nếu bàn đang có phiên), `checkout` (gọi lại trả kết quả đã chốt, `duplicate: true`), `my/checkin` (1 lần/ngày), `spin` (1 kết quả/vé), tạo đặt bàn (chống trùng giờ bằng khoá ghi).
- **Lỗi:** `{"detail": "<thông báo tiếng Việt>"}`; `422` cho dữ liệu sai định dạng.
- **Dữ liệu nhạy cảm:** mật khẩu chỉ lưu dạng scrypt; mật khẩu tạm chỉ trả đúng một lần khi tạo/đặt lại; nhật ký audit không chứa mật khẩu/token.

## Công khai và xác thực

| Phương thức, đường dẫn | Vai trò | Ghi chú |
|---|---|---|
| `GET /api/health` | ai cũng gọi | `{status, app: "manage"}` |
| `GET /api/public/venues/{slug}` | ai cũng gọi | chỉ trả `name`, `slug`; quán tạm ngưng = 404 |
| `POST /api/auth/login` | ai cũng gọi | `{login, password, venue_slug?}`; `venue_slug` chỉ cho khách. Khoá tài khoản 15 phút sau 5 lần sai; giới hạn 30 lần/5 phút/IP |
| `POST /api/auth/register` | ai cũng gọi | khách tự đăng ký **trong một quán**; SĐT chuẩn hoá `0xxxxxxxxx` |
| `GET /api/auth/me` | đã đăng nhập | trả thêm `csrf_token` |
| `POST /api/auth/logout` | đã đăng nhập | |
| `POST /api/auth/change-password` | đã đăng nhập | thu hồi phiên ở thiết bị khác; gỡ cờ `must_change_password` |

## Admin nền tảng (`/api/admin`, chỉ `platform_admin`)

| Đường dẫn | Ghi chú |
|---|---|
| `GET /overview` | số quán/tài khoản |
| `GET/POST /venues`, `GET/PATCH /venues/{id}` | tạo quán kèm chủ quán (mật khẩu tạm một lần); `PATCH` đổi tên/`ACTIVE`↔`SUSPENDED` (tạm ngưng thu hồi mọi phiên) |
| `POST /venues/{id}/owner/reset-password` | mật khẩu tạm mới, thu hồi phiên |
| `GET /venues/{id}/customers?q=` | tìm không dấu |
| `PATCH /users/{id}/status` | khoá/mở khoá chủ quán, nhân viên, khách (không áp dụng cho admin) |
| `GET /audit?limit=` | nhật ký hoạt động |

## Vận hành quán (`/api/venues/{venue_id}`)

Ký hiệu: **O** chủ quán, **S** nhân viên, **C** khách.

| Đường dẫn | Vai trò | Ghi chú |
|---|---|---|
| `GET /` | mọi vai trò trong quán, admin | thông tin quán |
| `GET /tables` | O S | kèm phiên đang chạy, tiền tạm tính do máy chủ tính |
| `POST /tables`, `PATCH /tables/{id}` | O | giá giờ 0–10.000.000; không ngừng dùng bàn đang chơi |
| `POST /tables/{id}/open` | O S | chốt giá giờ (`rate_snapshot`); 409 nếu đã có phiên |
| `GET /sessions/{id}/quote?voucher_id=` | O S | xem trước tiền, món, cọc, voucher khả dụng |
| `POST /sessions/{id}/checkout` | O S | `{payment_method: cash\|transfer, voucher_id?}`; làm tròn lên theo phút; trừ voucher rồi cọc |
| `POST /sessions/{id}/void` | O | chỉ phiên đang chơi, bắt buộc lý do |
| `POST/DELETE /sessions/{id}/items`, `PATCH /sessions/{id}/customer` | O S | chỉ khi phiên còn `ACTIVE` |
| `GET /sessions/{id}/invoice` | O S | chỉ phiên đã thanh toán |
| `GET /sessions` | O S | **nhân viên chỉ thấy hôm nay**; chủ quán lọc `status`, `table_id`, `date_from`, `date_to` |
| `GET /revenue/today` | O S | doanh thu hôm nay (giờ của quán) |
| `GET/POST /staff`, `PATCH /staff/{id}`, `POST /staff/{id}/reset-password` | O | |
| `GET /products` | O S | |
| `POST /products`, `PATCH /products/{id}` | O | |
| `GET/POST /customers`, `PATCH /customers/{id}/status` | O S (khoá: O) | khách tạo tại quầy nhận mật khẩu tạm |

## Đặt bàn và cọc giả lập

Cọc đi qua `PaymentProvider`; hiện chỉ có `mock` (**không thu tiền thật**, `MANAGE_PAYMENT_PROVIDER=mock`).

| Đường dẫn | Vai trò | Ghi chú |
|---|---|---|
| `GET/PUT /booking-settings` | đọc: O S C; ghi: O | cọc, thời gian giữ chỗ, hạn hoàn cọc, thời gian chờ khách |
| `GET /availability?date=` | C | khoảng bận của từng bàn, không lộ ai đặt |
| `GET/POST /my/bookings` | C | bước 30 phút, tối đa 14 ngày tới, tối đa 3 lịch chưa diễn ra |
| `POST /my/bookings/{id}/deposit/mock-pay` | C | giả lập trả cọc → `CONFIRMED`; giữ chỗ quá hạn → `EXPIRED` |
| `POST /my/bookings/{id}/cancel` | C | trước hạn hoàn cọc: hoàn; muộn: mất cọc |
| `GET /my/sessions` | C | lịch sử chơi của chính mình |
| `GET /bookings`, `POST /bookings/{id}/check-in\|no-show\|cancel` | O S | nhận bàn ≥ 30 phút trước giờ hẹn mở phiên gắn lịch; quầy huỷ luôn hoàn cọc |

## Gamification

| Đường dẫn | Vai trò | Ghi chú |
|---|---|---|
| `GET/PUT /game-settings` | O | chế độ check-in, điểm, mốc chuỗi ngày, thưởng đảm bảo tối thiểu/tối đa mỗi ngày |
| `GET/PUT /networks` | O | IP/CIDR của quán (tối đa 10; từ chối dải quá rộng) |
| `GET/PUT /wheel` | O | tổng tỷ lệ đúng 100%, cần ô "chúc may mắn" |
| `GET /game-stats` | O | check-in/quay hôm nay, thưởng đảm bảo đã phát |
| `GET /checkin-code` | O S | mã đổi theo chu kỳ (kỳ trước vẫn dùng được thêm một kỳ) |
| `GET /my/game`, `POST /my/checkin`, `POST /my/spins/{ticket_id}/spin` | C | kết quả quay do máy chủ quyết định bằng `secrets` |

## Báo cáo (chỉ chủ quán)

| Đường dẫn | Ghi chú |
|---|---|
| `GET /reports/revenue?date_from&date_to&group=day\|week\|month` | tối đa 366 ngày; doanh thu = tổng hoá đơn (sau voucher, trước trừ cọc) theo ngày chốt phiên; kèm theo bàn, dịch vụ bán chạy, phiên theo giờ bắt đầu |
| `GET /reports/export.csv?date_from&date_to` | UTF-8 có BOM; ô bắt đầu bằng `= + - @` được thêm dấu nháy để chống chèn công thức; ghi audit `report_exported` |

## Cấu hình môi trường

`MANAGE_DATABASE_URL`, `MANAGE_TIMEZONE`, `MANAGE_API_PORT`, `MANAGE_WEB_PORT`, `MANAGE_COOKIE_SECURE`, `MANAGE_ALLOWED_HOSTS`, `MANAGE_EXTRA_ORIGINS`,
`MANAGE_PAYMENT_PROVIDER` (chỉ `mock`), `MANAGE_TRUSTED_PROXIES` (CIDR của reverse proxy được tin `X-Forwarded-For`). Giá trị sai làm máy chủ **không khởi động**.
