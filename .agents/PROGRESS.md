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

## Phần chưa kiểm chứng / giới hạn

- Chưa huấn luyện model nào; chưa có số đo độ chính xác.
- Dữ liệu ít (84 clip, 2 camera, 5 video): chưa đủ cho ST-GCN/PoseC3D. WALKING quá ít nên augment không tạo dữ liệu mới.
- Câu hỏi mở: runtime ONNX (cv2.dnn hay onnxruntime); đồng ý ghi hình của quán/khách.
- Chưa chạy `npm test`, `npm run build`, `scripts/smoke.py` cho các thay đổi gần đây (chỉ đụng `services/labeling` và scripts).

## Bước tiếp theo (đề xuất)

1. Gán thêm nhãn: 36 clip INSUFFICIENT, ưu tiên WALKING (batch mới `--focus bent` hoặc thêm người gán).
2. Baseline nhỏ (GRU/1D-CNN) trong môi trường riêng để kiểm tra dữ liệu có học được không.
3. P0: đo baseline luật hiện tại bằng nhãn đã có.
