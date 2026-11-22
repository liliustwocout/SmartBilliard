# Tiến trình & checkpoint — nhận diện hành động (Hướng A → B)

Quy ước: sau mỗi bước hoàn thành, thêm một dòng vào "Nhật ký checkpoint" và cập nhật "Hiện trạng" / "Bước tiếp theo".
Kế hoạch gốc: `docs/planning/ACTION_RECOGNITION_PLAN.md`. Dữ liệu và nhãn nằm dưới `data/` (gitignored), không commit.

## Hiện trạng (cập nhật 2026-11-20)

| Giai đoạn | Trạng thái |
|---|---|
| P0 Đo baseline luật hiện tại | Chưa làm (mới có kiểm tra bằng mắt, mục 2b của kế hoạch) |
| P1 Hoàn thiện Hướng A | Chưa làm |
| P2 Gán nhãn | Batch `batch-20261120-003502`: xong vòng 1 + vòng chốt. 84 clip có nhãn dùng được, 36 clip INSUFFICIENT |
| P3 Dataset khung xương | Có xuất `.npz` + cân bằng lớp (tạm). Chưa theo định dạng MMAction2 |
| P4 Huấn luyện | Chưa làm (cần môi trường riêng, không cài vào `.venv`) |
| P5–P7 | Chưa làm |

Số liệu batch hiện tại (nhãn cuối): SHOOTING 26, AIMING 26, WATCHING 23, WALKING 9 (tính cả clip chưa dùng được ở tập con).
Tập dùng được là 84 clip; chia `--test-camera cam1 --val-video cam2_03.mp4`: train 34 / val 19 / test 31. WALKING chỉ 3 clip train, 2 clip test.

## Nhật ký checkpoint

- **CP1** — Gộp kết quả 4 thành viên (`scripts/merge_labels.py`): 120 clip có người gán; AGREED 75, REVIEW 9, INSUFFICIENT 36. Kappa theo cặp 0,69–1,0 trên 12–17 clip chung.
- **CP2** — Tạo pack chốt cho 9 clip REVIEW (`data/label_packs/batch-20261120-003502/pack_member-chot`). Người phụ trách chốt xong, gộp lại: 9 clip thành MAJORITY, REVIEW còn 0.
- **CP3** — Thêm `services/labeling/dataset.py` + `scripts/export_skeleton_dataset.py`: xuất `skeleton_dataset.npz` (24 khung × 17 điểm × x/y/conf), chia theo camera/video.
- **CP4** — Thêm cân bằng lớp tạm (`--balance`): augment lớp ít chỉ trên train + class_weights; có test hồi quy. Chưa huấn luyện nên chưa biết hiệu quả.
- **CP5 (phòng quản lý M0)** — Nhánh `feat/manage-m0`: khung `apps/manage_api` (config MANAGE_*, DB riêng, /api/health, host/origin check) + `apps/manage_web` (cổng 5174), thêm vào CI. Kế hoạch: `docs/planning/MANAGEMENT_ROOM_PLAN.md`. Chưa có auth/dữ liệu nghiệp vụ (M1).
- **CP6 (phòng quản lý M0.5)** — Design system "Nỉ bàn" trong `apps/manage_web`: tokens sáng/tối (mặc định sáng, không dùng shadow), font Barlow Condensed + Be Vietnam Pro (tự host), bộ component (Button, Field, Badge, Card, Skeleton, EmptyState, ErrorState, Tabs, DataTable, Modal, ConfirmDialog, Toast, TableCard, FeltTable), trang đăng nhập / tổng quan rỗng / `#/design`. 10 test, build đạt, đã xem ảnh desktop sáng-tối và mobile 375px (không cuộn ngang). Chưa thử iOS Safari/Android thật; chưa có biểu đồ/DateRange (M6).
- **CP7 (phòng quản lý M1)** — Backend: bảng `venues/users/auth_sessions/audit_log`, scrypt, cookie HttpOnly + CSRF, khoá 5 lần sai/15 phút, đổi mật khẩu bắt buộc (thu hồi phiên khác), `require_roles`, `venue_scope` (quán khác = 404), script `scripts/manage_create_admin.py`. Frontend: đăng nhập thật, đổi mật khẩu, đăng xuất. Smoke HTTP thật bằng curl đạt. Chưa có CRUD quán (M2), throttle IP chỉ trong bộ nhớ 1 process, chưa tin X-Forwarded-For.
- **CP8 (phòng quản lý M2)** — Admin: `apps/manage_api/admin.py` (overview, tạo/tìm/cập nhật quán, tạm ngưng thu hồi phiên, đặt lại mật khẩu chủ quán, khách theo quán, khoá/mở khoá tài khoản, tìm kiếm không dấu tiếng Việt) + 4 trang admin trong `manage_web`. Đã chạy thật trên trình duyệt: đăng nhập → tạo quán → mật khẩu tạm → chi tiết quán. Sửa lỗi hộp thoại bị lệch do Tailwind reset margin. Chưa có: đổi tên quán trên UI, xoá quán (cố ý chưa làm), CRUD nhân viên (M4).
- **CP9 (phòng quản lý M3)** — `venue_api.py`: bàn (CRUD, chủ quán), mở bàn (giá chốt, unique ACTIVE/bàn, 409 khi mở trùng), checkout idempotent (UPDATE có điều kiện + payment unique), huỷ phiên (chủ quán, bắt buộc lý do, chỉ phiên ACTIVE), lịch sử (nhân viên ép = hôm nay theo giờ quán), doanh thu hôm nay; `billing.py` độc lập với demo. UI: tổng quan bàn (poll 5s, đồng hồ chạy local, tiền lấy từ server), Bàn và giá, Lịch sử. Đã chạy thật trên trình duyệt: tạo bàn → mở → tính tiền → doanh thu cập nhật. Chưa làm: cọc bàn/PaymentProvider mock (gắn với đặt bàn ở M5), WebSocket (đang poll), báo cáo ngày khác (M6), bảng giá theo khung giờ.
- **CP10 (phòng quản lý M4)** — `shop_api.py`: nhân viên (chủ quán tạo/khoá/đặt lại mật khẩu), menu dịch vụ, món trong phiên (gộp cùng món cùng giá, giá chốt, khoá ghi bằng UPDATE rỗng có điều kiện ACTIVE để checkout không bỏ sót/đếm đôi món), gắn khách, hoá đơn, khách do quầy tạo (SĐT chuẩn hoá, mật khẩu tạm). `play_sessions` có thêm `table_amount/items_amount`; DB tạo trước M4 cần tạo lại (chưa có migration). UI: Nhân viên, Menu, Khách hàng, món/khách trong hộp thoại tính tiền, hoá đơn + In. Đã chạy thật: gọi món → thu tiền → hoá đơn 21.000 ₫ → doanh thu cập nhật. Chưa: in thử trên máy in thật, tự đăng ký khách (M5).
- **CP11 (phòng quản lý M5)** — Khách tự đăng ký theo quán (`/api/auth/register`, tài khoản riêng từng quán), `booking_api.py` (đặt bàn kèm cọc giả lập qua `PaymentProvider` mock; PENDING giữ chỗ → CONFIRMED; hết hạn lazily; chống trùng giờ bằng khoá ghi; tối đa 3 lịch chưa diễn ra/khách; huỷ hoàn/mất cọc theo `refund_before_minutes`; quầy huỷ luôn hoàn; không đến sau thời gian chờ → mất cọc; nhận bàn mở phiên gắn lịch; checkout trừ cọc, cọc thừa hoàn; doanh thu = tổng hoá đơn gộp). `play_sessions` thêm `booking_id`, `deposit_applied` (DB cũ cần tạo lại). UI khách mobile-first (thanh điều hướng đáy, lưới giờ 30 phút theo giờ VN UTC+7), UI quầy (Đặt bàn + luật cọc). Đã chạy thật: đăng ký → đặt → cọc giả lập → quầy thấy lịch; nhận bàn sớm hơn 30 phút bị từ chối đúng. Chưa: thanh toán thật, nhắc lịch (SMS/thông báo), giờ mở cửa của quán, gamification (M5b).

## Phần chưa kiểm chứng / giới hạn

- Chưa huấn luyện model nào; chưa có số đo độ chính xác.
- Dữ liệu ít (84 clip, 2 camera, 5 video): chưa đủ cho ST-GCN/PoseC3D. WALKING quá ít nên augment không tạo dữ liệu mới.
- Câu hỏi mở: runtime ONNX (cv2.dnn hay onnxruntime); đồng ý ghi hình của quán/khách.
- Chưa chạy `npm test`, `npm run build`, `scripts/smoke.py` cho các thay đổi gần đây (chỉ đụng `services/labeling` và scripts).

## Bước tiếp theo (đề xuất)

1. Gán thêm nhãn: 36 clip INSUFFICIENT, ưu tiên WALKING (batch mới `--focus bent` hoặc thêm người gán).
2. Baseline nhỏ (GRU/1D-CNN) trong môi trường riêng để kiểm tra dữ liệu có học được không.
3. P0: đo baseline luật hiện tại bằng nhãn đã có.
