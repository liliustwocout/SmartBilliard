# Rà soát và chốt dữ liệu — 21/11/2026

Đã làm phần rà soát: kiểm tra đủ **1.349 khung hình mẫu** trong 60 clip (36 cũ, 24 mới), kiểm tra danh tính người trong box, phân biệt đi lại/đứng xem và loại hành động ngoài bốn lớp. Đã đối chiếu 28 box gậy với khung hình độ phân giải gốc và xem đủ 72 crop âm. 60 clip đều có quyết định giữ/loại; không còn clip chưa có quyết định trong lượt rà soát này.

## Nhãn hành động đã chốt

- 36 clip cũ: giữ 2 clip (1 WALKING, 1 WATCHING), loại 33 INVALID và 1 UNSURE (xếp bi). Hai clip từng để UNSURE được sửa thành INVALID vì box trôi hoặc đổi người.
- 24 clip mới: giữ 14 clip (13 WALKING, 1 WATCHING), loại 5 INVALID và 5 UNSURE. Một clip WALKING cũ bị loại do xen đi lại/dừng/bôi lơ; thay bằng đoạn đi lại rõ ràng của một clip trước đó để UNSURE.
- Cắt 9 clip ở ranh giới hành động để giữ đoạn rõ ràng ít nhất hai giây. Frame, box, keypoint và thời gian video được cắt đồng bộ; vị trí đoạn gốc lưu trong `review_span`.
- Giữ nguyên 84 nhãn đồng thuận có sẵn. Bộ gộp có **100 clip**: SHOOTING 26, AIMING 26, WATCHING 25, **WALKING 23**. Không ép clip xe máy/đổi ID thành WALKING để tăng số lượng.

Đây là AI rà soát và chốt nhãn theo yêu cầu, không giả là hai người độc lập đã kiểm tra. 16 nhãn mới mang `AI_ADJUDICATED`; không sửa phiếu của thành viên, không cộng AI vào kappa. Nhãn bị loại đã có quyết định `EXCLUDE` và lý do, không còn nằm ở danh sách chờ quyết định của lượt rà soát này.

Artifact riêng dưới `data/label_packs/review-20261121/`:

- `old_adjudication.json`, `new_adjudication.json`: quyết định và bằng chứng từng clip.
- `old_final/`, `new_final/`: nhãn chốt, clip index đã cắt, danh sách loại và hash nguồn.
- `skeleton_reviewed.npz`: dữ liệu keypoint (100, 24, 17, 3), có batch ID, clip ID gốc, trạng thái nhãn và nguồn AI/đồng thuận.
- `skeleton_reviewed_manifest.json`: số lượng, split và SHA-256 của NPZ.
- `review_completion.json`, `completion_checks.json`: kết quả hoàn tất, hash đầu ra và xác nhận nguồn cũ không đổi.

Chia theo nguồn video: train 43, val 23 (`cam2_03.mp4`), test 34 (toàn camera `cam1`). Cả bốn lớp xuất hiện trong từng split. Chỉ train được cân bằng thành 48 mẫu, gồm 5 bản augmentation; val/test không tăng mẫu. Đây chưa phải kết quả huấn luyện model hành động.

## Box gậy và ảnh âm

Rà soát 28 box: **sửa 6**, giữ nguyên 19, loại 3 ảnh che khuất/không chắc đầu gậy. Các lỗi sửa gồm cắt hụt đuôi gậy đứng, cắt hụt mũi gậy lúc ngắm và box chưa phủ hết phần gậy thấy được. 72 crop âm không có gậy nhìn thấy được và được giữ nguyên.

Dataset mới `data/datasets/cue_reviewed_20261121/` có **97 ảnh**: train 63 (15 dương, 48 âm), val 18 (6 dương, 12 âm), test 16 (4 dương, 12 âm). Mỗi frame dương chỉ giữ một crop đã đối chiếu; bỏ các crop phóng khác từ cùng frame. Hash ảnh không trùng, không có video nằm ở nhiều split. Bộ cũ không bị ghi đè.

`box_review_decisions.json` lưu box cũ/mới và lý do loại; `corrected_boxes.jpg` là ảnh đối chiếu sáu box sửa. Manifest ghi `review_complete=true`, `annotation_source=AI_ADJUDICATION`, `human_reviewed=false`. Đây vẫn là ground truth do AI chốt cho các crop được chọn, không phải ground truth toàn khung hình hoặc nghiệm thu tại quán.

## Huấn luyện và kiểm tra

Đã huấn luyện lại từ best v2 bằng bộ nhãn đã sửa: input 640, batch 8, CPU, không khóa backbone, không mosaic/xoay, scale 0,3, AdamW lr 0,0005, seed 0, tối đa 40 epochs, patience 8. Lần chạy dừng sớm ở epoch 27, best epoch 19.

So sánh cả hai checkpoint trên **cùng validation đã sửa**, gồm 18 crop / 6 box gậy:

| Checkpoint | mAP50 | mAP50–95 |
|---|---|---|
| V2 trước rà soát | 0,5487 | **0,2743** |
| V3 huấn luyện bằng nhãn đã sửa | 0,4745 | 0,1687 |

V3 kém hơn theo tiêu chí đã chọn nên giữ nguyên V2 trong `models/yolov8n-cue.onnx`; không thay bằng model kém hơn hoặc coi nhãn đã sửa là bằng chứng model đã đạt. SHA-256 model vẫn là `a025168b1d3f069f1354d3d84da740e1e2e8353ada7ae178a774a3bd9ce73283`. Cả hai checkpoint và cấu hình lần train được giữ local; `training_comparison.json` lưu phép so sánh.

Đã chạy lại adapter OpenCV trên bộ crop đã sửa, ngưỡng confidence 0,35 / IoU 0,5: validation 1 TP, 2 FP, 5 FN; diagnostic test 0 TP, 1 FP, 4 FN. Đoạn video thật từ giây 168–192 vẫn có **0 detection gậy trên 94 frame mẫu**. Model chưa đạt toàn cảnh; `validated=false` và cơ chế lọc gậy khỏi quyết định mở bàn giữ nguyên. Bộ test đã dùng debug, không gọi là holdout độc lập mới.

Artifact của lần chạy trong `data/datasets/cue_reviewed_20261121/`: `runs/reviewed_v3/`, `training_comparison.json`, `diagnostic_selected/runtime_report.json` và `diagnostic_selected/cue_preview.mp4`. Video là đầu ra nhận diện thật, không chèn box nhãn tay làm detection.

Kiểm tra cuối: **139 test Python passed**, **11 test frontend passed**, production build **PASS**, HTTP/WS smoke sau build với SQLite tạm **PASS**, `git diff --check` **PASS**. Hash xác nhận clip index và 84 nhãn đồng thuận gốc không đổi; 97 ảnh mới khớp manifest. Không đổi API nghiệp vụ, không thay `.env`, không ghi đè SQLite.

Phần rà soát/chốt nhãn cho thử nghiệm local đã hoàn tất, không yêu cầu tạo thêm phiếu người giả. Nguồn 16 nhãn mới và box gậy được giữ rõ là AI; việc này không thay cho kiểm chứng camera bằng video độc lập và dữ liệu thực địa đa dạng hơn.
