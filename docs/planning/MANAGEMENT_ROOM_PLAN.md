# Kế hoạch "Phòng quản lý" (sản phẩm thật) — tách biệt với phòng demo

Ngày: 22/11/2026. Đây là **kế hoạch**, chưa có code. Dựa trên hiện trạng: `apps/api` + `apps/web` là phòng demo (SQLite một quán, không đăng nhập, chỉ bind loopback, có mô phỏng/camera/lab/ROI).

## 1. Nguyên tắc tách biệt

| | Phòng demo (giữ nguyên) | Phòng quản lý (mới) |
|---|---|---|
| Mã nguồn | `apps/api`, `apps/web` | `apps/manage_api`, `apps/manage_web` |
| Cổng dev | API 8000 / web 5173 | API 8100 / web 5174 |
| Database | `data/smartbilliard.db` | `data/manage.db` (file riêng, đổi được qua `MANAGE_DATABASE_URL`) |
| Người dùng | Không có | Admin / Chủ quán / Nhân viên / Khách |
| Dữ liệu | Mô phỏng, video thử | Chỉ dữ liệu thật, không có endpoint mô phỏng |

Quy tắc cứng:
- `manage_*` **không import** từ `apps/api`/`apps/web`; không dùng chung DB, `.env` key, runtime_settings. Phần dùng chung (tính tiền làm tròn, tiện ích thời gian) tách thành module thuần `services/common/` (không phụ thuộc FastAPI/UI), demo có thể chuyển sang dùng sau, không bắt buộc.
- Không có simulation/lab/ROI/video trong phòng quản lý. Camera/AI là giai đoạn cuối, tuỳ chọn, và **không tự tính tiền** (theo AGENTS.md).
- Không sửa hành vi phòng demo; test demo hiện có phải vẫn xanh.

## 2. Vai trò và phạm vi dữ liệu

- **Admin nền tảng** (`platform_admin`): tạo/khoá quán, tạo tài khoản chủ quán, xem danh sách khách theo từng quán, audit. Không thao tác bàn/tiền thay quán (chỉ xem tổng hợp).
- **Chủ quán** (`owner`): toàn quyền trong quán của mình: bàn, giá, nhân viên, khách, menu, báo cáo.
- **Nhân viên** (`staff`): mở bàn, thêm dịch vụ, checkout, xem lịch sử; không đổi giá, không xoá dữ liệu, không xem báo cáo doanh thu tổng (cấu hình được).
- **Khách** (`customer`): thuộc **một quán**; xem bàn trống, đặt bàn, xem lịch sử chơi/hoá đơn của chính mình.

Cô lập: mọi bảng nghiệp vụ có `venue_id`; mọi truy vấn đi qua một lớp `scoped_query(venue_id)`; test bắt buộc "chủ quán A không đọc/sửa được dữ liệu quán B" và "khách quán A không đăng nhập được quán B". Khách cùng số điện thoại ở hai quán là hai bản ghi độc lập.

## 3. Mô hình dữ liệu (SQLite, SQLAlchemy)

- `users` (id, role, email/phone, password_hash, venue_id nullable, status, must_change_password, created_at UTC)
- `venues` (id, name, slug, status ACTIVE/SUSPENDED, plan, owner_user_id, timezone)
- `customers` (id, venue_id, user_id nullable, name, phone, note) — khách vãng lai không cần tài khoản
- `billiard_tables` (id, venue_id, name, type, status, hourly_rate hiện tại)
- `price_rules` (venue_id, table_type, khung giờ, giá/giờ) — giá chốt vào phiên bằng snapshot
- `play_sessions` (id, venue_id, table_id, customer_id nullable, started_at, ended_at, status ACTIVE/PAID/VOID, rate_snapshot, opened_by, closed_by) + unique partial index một ACTIVE/bàn (như demo)
- `session_items` / `products` (menu đồ uống, dịch vụ; giá snapshot)
- `invoices` / `payments` (tổng tiền bàn + dịch vụ, phương thức tiền mặt/chuyển khoản ghi nhận thủ công; **chưa tích hợp cổng thanh toán**)
- `bookings` (venue_id, table_id, customer_id, start/end, status)
- `auth_sessions` (token băm, user_id, hết hạn), `audit_log` (ai, làm gì, trước/sau, thời điểm)

Quy ước giữ như AGENTS.md: UTC, VND số nguyên, backend là nguồn thời gian/giá/tiền, idempotency cho mở bàn/checkout, không mở trùng ACTIVE.

## 4. Xác thực và bảo mật

- Băm mật khẩu bằng `hashlib.scrypt` (stdlib) — kiểm tra thêm `argon2-cffi` nếu đã có trong `requirements`; không thêm hạ tầng.
- Phiên đăng nhập: token ngẫu nhiên lưu băm trong DB, gửi bằng cookie `HttpOnly; SameSite=Lax` (+ `Secure` khi HTTPS), CSRF token cho request ghi. Không dùng JWT cho MVP.
- Phân quyền bằng dependency `require_role(...)` trên **từng endpoint**; ẩn nút ở React chỉ là UX.
- Admin tạo tài khoản chủ quán bằng mật khẩu tạm + buộc đổi lần đầu; khoá đăng nhập sau N lần sai; rate-limit login.
- Admin đầu tiên tạo bằng script `scripts/manage_create_admin.py` (mật khẩu qua env/prompt, không commit).
- Bind loopback mặc định; mở LAN/Internet chỉ sau khi có HTTPS, `ALLOWED_ORIGINS`, rà soát bảo mật (xem `SYSTEM_ARCHITECTURE.md`, "Ranh giới tin cậy").
- Audit log cho: đổi giá, mở/đóng/huỷ phiên, checkout, tạo/khoá tài khoản, đổi vai trò.

## 5. Các trang

**Admin** (`/admin`): đăng nhập · danh sách quán (tạo, khoá/mở, đặt lại mật khẩu chủ) · chi tiết quán (chủ quán, số bàn, số khách, trạng thái) · khách theo quán (tìm, khoá) · audit log · tổng quan hệ thống.

**Chủ quán / nhân viên** (`/shop`): tổng quan bàn (mở/đóng/checkout, đồng hồ, tiền tạm tính) · quản lý bàn & bảng giá · phiên chơi & lịch sử (lọc ngày, in hoá đơn) · menu dịch vụ · khách hàng (CRUD, lịch sử) · đặt bàn (lịch) · báo cáo doanh thu (ngày/tuần/tháng, theo bàn) · nhân viên (tạo, phân quyền, khoá) · cài đặt quán.

**Khách** (`/c/<slug-quán>`): đăng ký/đăng nhập theo quán · xem bàn trống · đặt/huỷ bàn · lịch sử chơi và hoá đơn của mình · hồ sơ.

Frontend: React + TypeScript strict + Tailwind như hiện tại; một app `manage_web` với 3 khu vực route theo vai trò, UI tiếng Việt, responsive (khách dùng điện thoại).

## 6. Lộ trình (mỗi mốc nhỏ, có test, commit riêng, nhánh `feat/manage-*`)

| Mốc | Nội dung | Tiêu chí xong |
|---|---|---|
| M0 | Khung `manage_api`/`manage_web`, DB riêng, health, config, CI chạy cả hai | Hai app chạy song song cổng khác nhau; test demo vẫn xanh |
| M1 | Xác thực + vai trò + cô lập quán + script tạo admin + audit | Test cô lập chéo quán, login sai/khoá, CSRF |
| M2 | Admin: CRUD quán, tài khoản chủ quán, khoá/mở, xem khách theo quán | Admin thao tác đủ luồng qua UI |
| M3 | Chủ quán: bàn, giá, mở/đóng/checkout phiên, lịch sử | Regression: không trùng ACTIVE, giá snapshot, idempotent checkout |
| M4 | Nhân viên + phân quyền, menu dịch vụ, hoá đơn, khách quán | Staff bị chặn đổi giá ở **backend** |
| M5 | Khu khách: đăng ký theo quán, đặt bàn, lịch sử | Khách A không thấy dữ liệu khách B / quán khác |
| M6 | Báo cáo doanh thu, xuất CSV, sao lưu DB, README + API_SPEC + ADR | Số liệu báo cáo khớp tổng hoá đơn trong test |
| M7 (tuỳ chọn, sau) | Cầu nối camera/AI → gợi ý mở bàn cho nhân viên xác nhận | Chỉ khi có kiểm chứng video thật; không tự tính tiền |

Kiểm tra trước bàn giao mỗi mốc: `pytest` (SQLite tạm), `npm test`, `npm run build`, smoke script riêng `scripts/manage_smoke.py`.

## 7. Rủi ro và giới hạn

- SQLite một process phù hợp vài quán thử nghiệm; nhiều quán thật cần PostgreSQL và migration (Alembic) — chốt ở ADR trước M2 nếu mục tiêu là nhiều quán đồng thời.
- Thanh toán chỉ **ghi nhận thủ công**; chưa có cổng thanh toán/VNPay/MoMo.
- Dữ liệu cá nhân khách (SĐT, tên): cần chính sách lưu/xoá, không đưa vào log/test.
- Chưa thiết kế đồng bộ cloud ↔ PC quán trong `DESKTOP_PRODUCT_DEPLOYMENT.md`; kế hoạch này là web một server, chưa phải bản cài `.exe`.

## 8. Quyết định đã chốt (22/11/2026)

1. **Một server cho nhiều quán** (multi-tenant, cô lập theo `venue_id`).
2. **Khách có tài khoản riêng** để dùng gamification (mục 9).
3. **Bản đầu làm đủ chức năng**; **cọc bàn là mock**: bảng `deposits` + trạng thái PENDING/PAID/REFUNDED do nút giả lập cổng thanh toán đổi, gắn rõ nhãn "MÔ PHỎNG" trên UI và API, không thu tiền thật, không lưu thông tin thẻ. Giao diện `PaymentProvider` để sau thay bằng VNPay/MoMo.
4. **Nhân viên chỉ xem doanh thu của ngày hôm nay** (theo múi giờ quán): backend ép khoảng thời gian = hôm nay cho vai trò `staff`, bỏ qua tham số ngày client gửi; báo cáo tuần/tháng/theo bàn chỉ chủ quán.

## 9. Gamification (đã chỉnh theo yêu cầu 22/11/2026)

Phạm vi theo từng quán (điểm/phần thưởng quán A không dùng ở quán B). Gồm 4 khối:

### 9.1 Check-in qua wifi quán
- Trình duyệt **không đọc được tên wifi**, nên xác minh bằng **IP công cộng của quán**: chủ quán đăng ký một hoặc nhiều IP/CIDR trong cài đặt; khách bấm "Check-in" trên web/điện thoại, server so địa chỉ nguồn của request với danh sách đó. Chỉ tin `X-Forwarded-For` khi request đến từ reverse proxy đã khai báo.
- Lớp bổ sung (chủ quán bật được): **mã QR xoay vòng** dán tại quầy (đổi mỗi vài phút) để chống khách ở ngoài dùng chung IP/VPN.
- Luật: mỗi khách **1 check-in/ngày/quán** (theo múi giờ quán, key `customer_id + ngày`), idempotent; check-in được ghi `ip`, `method` (wifi/QR), thời điểm.
- Giới hạn cần ghi rõ: IP sau CGNAT/chung toà nhà có thể trùng người ngoài quán; VPN có thể giả IP. Vì vậy phần thưởng chỉ là điểm/voucher trong app, không phải tiền mặt.

### 9.2 Chuỗi check-in (streak)
- Check-in ngày liên tiếp → `streak` tăng; bỏ lỡ một ngày → về 0 (chủ quán chọn có cho "ngày miễn trừ" 1 lần/tuần hay không).
- Điểm check-in cơ bản + **bonus theo mốc** (3/7/14/30 ngày) — bảng mốc và điểm do chủ quán cấu hình.
- Mọi điểm ghi vào sổ `xp_ledger` (chỉ thêm, không sửa), idempotent theo (khách, ngày). Có thể đổi điểm lấy phần thưởng như đề xuất cũ; điểm từ phiên chơi chỉ cộng khi nhân viên checkout (không từ tín hiệu camera).

### 9.3 Vòng quay may mắn
- Mỗi check-in hợp lệ → **1 lượt quay** (có thể thêm lượt thưởng ở mốc streak). Lượt quay hết hạn trong ngày hoặc N ngày (cấu hình).
- Chủ quán tự tạo **ô thưởng**: tên, loại (điểm / voucher giảm giá / giờ chơi miễn phí / "chúc may mắn"), giá trị, **trọng số/tỷ lệ %**, số lượng tồn tối đa, hạn dùng. Validate: tổng tỷ lệ = 100%, không âm; hiển thị tỷ lệ công khai cho khách.
- Quay ở **backend** bằng `secrets` (CSPRNG); kết quả ghi `spin_results` (ô trúng, tỷ lệ tại thời điểm quay, thời điểm). Client chỉ chạy animation theo kết quả server trả — không tự quyết kết quả. Mọi thay đổi tỷ lệ ghi audit log và áp dụng cho lượt quay sau đó.
- Trúng voucher → `reward_redemptions` mã dùng một lần; nhân viên xác nhận khi dùng, trừ vào hoá đơn.

### 9.4 Bắt buộc có 1–2 phần thưởng thật mỗi ngày
- Cài đặt theo quán: `min_daily_prizes` (0–2), `max_daily_prizes` (ngân sách chặn trên), `expected_daily_checkins` (N), danh sách ô được tính là "phần thưởng" (không tính "chúc may mắn").
- Cơ chế: đầu ngày (hoặc lười khi có check-in đầu tiên) server **bốc ngẫu nhiên k = min_daily_prizes vị trí lượt quay** trong 1..N làm "lượt đảm bảo trúng" (loại ô chọn theo trọng số các ô thưởng còn tồn). Lượt quay rơi vào vị trí đó **trúng chắc chắn**; các lượt khác quay theo tỷ lệ thường (không vượt `max_daily_prizes`).
- Nếu trong ngày có nhiều hơn N lượt mà vị trí đảm bảo chưa dùng (do thay đổi N giữa ngày) → ép trúng ở lượt kế tiếp. Nếu ngày đó **ít hơn k lượt quay** thì không thể đảm bảo; ghi rõ trong UI cấu hình ("đảm bảo khi có tối thiểu k lượt").
- Vì lượt đảm bảo nằm ngẫu nhiên nên khách không đoán được lượt nào trúng; thống kê "đã phát/đã đảm bảo hôm nay" chỉ chủ quán thấy.

### 9.5 Chống gian lận và tuân thủ
- Giới hạn: 1 check-in/ngày, 1 tài khoản/SĐT/quán, rate-limit endpoint quay, khoá tài khoản nghi ngờ.
- Phần thưởng là điểm/voucher dùng tại quán, không quy đổi tiền. Cần **kiểm tra quy định khuyến mại/quay thưởng** (thông báo cơ quan quản lý nếu áp dụng) trước khi chạy thật; kế hoạch này chưa phải tư vấn pháp lý.
- Cấp độ, huy hiệu, bảng xếp hạng (cho phép nickname ẩn danh) giữ như đề xuất trước, ưu tiên thấp hơn vòng quay/streak.

Bảng mới: `venue_networks` (IP/CIDR), `checkins`, `streaks`, `xp_ledger`, `wheel_prizes`, `wheel_daily_plan`, `spin_tickets`, `spin_results`, `rewards`, `reward_redemptions`, `badges`, `customer_badges`, `deposits`.

## 10. Điều chỉnh lộ trình

- M3 thêm: `PaymentProvider` mock + cọc bàn.
- M5 gồm: đăng ký/đăng nhập khách, đặt bàn kèm cọc mock, hồ sơ.
- **M5b (mới)**: check-in wifi/QR → streak → sổ XP → vòng quay (tỷ lệ chỉnh được, lượt đảm bảo 1–2 thưởng/ngày) → đổi thưởng/voucher; trang cấu hình vòng quay cho chủ quán. Huy hiệu/xếp hạng làm sau cùng.
- M6: báo cáo cho chủ quán; widget "doanh thu hôm nay" cho nhân viên.
- Test bắt buộc thêm: staff không lấy được doanh thu ngày khác; XP không cộng đôi khi checkout lặp; điểm không rò chéo quán; check-in từ IP lạ bị từ chối; check-in lặp trong ngày không cộng thêm; streak qua ngày/múi giờ; tổng tỷ lệ ≠ 100% bị từ chối; mô phỏng nhiều ngày với seed cố định luôn đủ `min_daily_prizes` và không vượt `max_daily_prizes`/tồn kho; khách không biết hay ép được kết quả quay từ client.

## 11. UI/UX (yêu cầu 22/11/2026: đẹp nhất có thể)

Cách làm: dùng skill `frontend-design` khi dựng giao diện; **chốt design system trước khi code trang** (mốc M0.5), rồi mới làm từng khu vực.

### 11.1 Nền tảng thiết kế
- **Hướng thẩm mỹ:** có bản sắc riêng cho bi-a (nỉ xanh đậm, gỗ, vàng đồng, ánh đèn bàn) thay vì giao diện admin mẫu; chọn font Việt hỗ trợ đầy đủ dấu, 1 font hiển thị + 1 font nội dung.
- **Design tokens** (màu, cỡ chữ, khoảng cách, bo góc, đổ bóng, chuyển động) ở một nơi; **dark mode + light mode** (quán tối hay dùng dark); đạt tương phản WCAG AA.
- **Thư viện component dùng chung** trong `manage_web`: Button, Input, Select, Modal/Drawer, Toast, Table dữ liệu, Tabs, Badge, Skeleton, EmptyState, ConfirmDialog, DateRange, Chart. Không copy-paste UI giữa các trang.
- Biểu đồ và dashboard theo skill `dataviz` (màu nhất quán, đọc được cả hai chế độ sáng/tối).

### 11.2 Theo từng đối tượng
- **Chủ quán/nhân viên (màn hình quầy, hay dùng tablet/PC):** tổng quan bàn dạng thẻ lớn, trạng thái nhìn là hiểu (trống/đang chơi/đặt trước), đồng hồ chạy và tiền tạm tính nổi bật; mở bàn và checkout **tối đa 2 chạm**; vùng bấm lớn, phím tắt trên PC; cập nhật realtime qua WebSocket; màn checkout in/gửi hoá đơn gọn.
- **Admin:** bảng dữ liệu mật độ cao nhưng thoáng: tìm kiếm, lọc, sắp xếp, phân trang, thao tác hàng loạt, xác nhận rõ ràng cho hành động khoá/xoá.
- **Khách (mobile-first):** dùng chủ yếu trên điện thoại; thanh điều hướng dưới; check-in một nút; **vòng quay may mắn là điểm nhấn**: animation mượt (chạy ở client nhưng đích dừng do server quyết định), hiệu ứng trúng thưởng (confetti/âm thanh bật tắt được), hiển thị tỷ lệ minh bạch; streak dạng lịch có ngọn lửa/mốc thưởng; huy hiệu, cấp độ có hình minh hoạ.
- **Trang chủ/landing theo quán** (`/c/<slug>`): ảnh, giờ mở cửa, bàn trống, nút check-in và đặt bàn nổi bật.

### 11.3 Chất lượng trải nghiệm
- Mọi màn có đủ 4 trạng thái: đang tải (skeleton), trống, lỗi (có hướng xử lý), thành công (toast).
- Chuyển động tinh tế, tôn trọng `prefers-reduced-motion`; không để animation chặn thao tác.
- Responsive đủ 3 cỡ: điện thoại, tablet, desktop; không cuộn ngang trang.
- Truy cập: điều hướng bằng bàn phím, focus rõ, nhãn form, `aria-live` cho toast/đồng hồ.
- Ngôn ngữ UI tiếng Việt tự nhiên, định dạng tiền VND và ngày giờ theo múi giờ quán; cố định một bộ thuật ngữ.
- Hiệu năng: tách bundle theo khu vực (admin/shop/customer), ảnh nén, đồng hồ bàn cập nhật cục bộ không re-render cả trang.

### 11.4 Cách kiểm chứng
- Mỗi mốc có chụp ảnh màn hình (trình duyệt trong app) ở mobile/tablet/desktop và dark/light để rà soát bằng mắt trước khi bàn giao.
- Test component (vitest) cho 4 trạng thái chính; kiểm tra tương phản bằng công cụ tự động; thử tay luồng khách trên viewport 375px.
- Ghi rõ trong báo cáo mốc những phần chưa kiểm thử trên thiết bị thật (iOS Safari, Android).

### 11.5 Điều chỉnh lộ trình
- Thêm **M0.5 – Design system**: tokens, font, bộ component, trang mẫu (đăng nhập, dashboard rỗng) ở cả sáng/tối trước khi làm M1 trở đi.
- Mỗi mốc M2–M6 có hạng mục "đánh bóng UI" nằm trong tiêu chí xong, không để dồn cuối.
