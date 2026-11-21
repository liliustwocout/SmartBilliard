# Thử nghiệm gậy và bổ sung nhãn — 20/11/2026

Bản ghi dưới đây là mốc 20/11. Phần rà soát đã được làm tiếp và chốt ngày 21/11; xem [nhãn đã chốt, dataset sửa và kết quả train lại](LABEL_REVIEW_20261121.md).

## Gán nhãn hành động

Gói `batch-20261120-003502` có 120 clip, 84 nhãn chốt của nhóm và 36 clip `INSUFFICIENT`. Phần lớn clip đó đã được hai người đánh dấu `INVALID`, không phải chưa ai gán nhãn.

AI đã xem chuỗi ảnh lấy mẫu của cả 36 clip; xem toàn sprite ở ca khó. Kết quả đề xuất: **31 INVALID, 3 UNSURE, 1 WATCHING, 1 WALKING**. Các lỗi chính là xe máy bị phát hiện thành người, box trôi khỏi người và đổi ID. Xếp bi hoặc hành động lẫn nhiều trạng thái không bị ép thành AIMING/WALKING.

Tạo gói mới `batch-20261120-221922` từ năm video quán, lấy mẫu 4 FPS trong 120 giây đầu, bỏ các khoảng đã xuất ở hai batch cũ. `--focus walking` chọn được **24** ứng viên, không phải 48 như giới hạn tối đa. AI đề xuất **13 WALKING, 1 WATCHING, 5 UNSURE, 5 INVALID** sau khi xem chuỗi ảnh. Điều này bổ sung 14 đề xuất WALKING (1 cũ, 13 mới), chưa làm tăng số nhãn chốt của người.

Các artifact riêng, bị gitignore:

- `data/label_packs/batch-20261120-003502/ai_review_20261120/ai_review.json`: lý do và frame đã xem của 36 clip.
- `data/label_packs/batch-20261120-003502/review_36_20261120/`: hai gói 36 clip để hai người rà soát độc lập.
- `data/label_packs/batch-20261120-221922/ai_review_20261120/ai_review.json`: nhãn đề xuất cho 24 clip mới.
- `data/label_packs/batch-20261120-221922/pack_member-1.zip` đến `pack_member-4.zip`: mỗi gói 12 clip, mỗi clip giao hai thành viên.

`smartbilliard-ai-review-v1` không được nhận làm file phiếu của thành viên. Mỗi đề xuất có `annotation_source=AI_VISUAL_REVIEW`, `human_review_required=true` và thời gian UTC. Không ghi đè kết quả cũ, không thêm phiếu người giả, không tính nhãn AI vào kappa. Chưa train model hành động từ nhãn đề xuất.

## Dataset gậy

Nhãn hành động không phải box gậy. Tạo dataset mới `data/datasets/cue_bootstrap_20261120/`, không dùng dataset `cue_v1` cũ vốn chỉ có một ảnh mô phỏng và nhãn rỗng.

36 khung hình thật được lấy từ năm video. Chỉ các vùng crop đã xem mới được dùng; **không phải ground truth đầy đủ của toàn khung hình**. Có 28 box gậy được AI đánh dấu bằng mắt trên 28 frame (18 train, 6 val, 4 test). Từ đó tạo 136 ảnh crop: train 102 (54 dương, 48 âm), val 18 (6 dương, 12 âm), test 16 (4 dương, 12 âm). Các crop train khác nhau của cùng frame không phải mẫu độc lập.

Chia theo video: train `cam1_01`, `cam1_02`, `cam2_02`; val `cam2_01`; test `cam2_03`. Mọi crop của một video ở cùng split. Nhãn, tọa độ crop và SHA-256 ảnh lưu trong `manifest.json`; `human_reviewed=false`. Ảnh âm gồm nếp phủ bàn, ghế, sàn, tường và dây — các nền có thể gây nhầm đường thẳng.

## Model và kiểm chứng

**Kết luận: đã train và nạp được ONNX, model chưa đạt nhận diện gậy trên toàn cảnh.** Không bật gate kiểm chứng hay tính tiền từ model này.

Môi trường riêng ở `data/datasets/cue_bootstrap_20261120/.venv`, dùng PyTorch 2.7.1 CPU, Ultralytics 8.4.216, ONNX 1.23.2, không sửa `.venv` runtime. Base là YOLOv8n, input 640, batch 8, tối đa 60 epochs, patience 15, workers 0, seed 0. Dataset, log và weights chỉ lưu local.

| Lần chạy | Thiết lập chính | Best epoch | mAP50 val | mAP50–95 val |
|---|---|---|---|---|
| Bootstrap v1 | Fine-tune toàn model, augmentation mặc định của script | 16 | 0,3228 | 0,0824 |
| Fine-tune v2 | Từ best v1, freeze 10 lớp, bỏ mosaic/xoay, scale 0,2, AdamW lr 0,001 | 20 | 0,5473 | 0,3072 |

V2 dừng sớm ở epoch 35. Chọn best v2 bằng mAP50–95 **validation**, lưu thành `models/yolov8n-cue.onnx`, FP32, opset 12, output `(1, 5, 8400)`. SHA-256: `a025168b1d3f069f1354d3d84da740e1e2e8353ada7ae178a774a3bd9ce73283`. Bản đầu được giữ ở `data/datasets/cue_bootstrap_20261120/baseline_v1/`. Metadata model ghi nguồn nhãn AI, `human_reviewed=false`, `validated=false` và trạng thái chưa đạt toàn cảnh.

Đã đối chiếu OpenCV/PyTorch trên ba crop của các split; điểm confidence lớn nhất khớp trong khoảng 0,000001. Đây chỉ là kiểm tra xuất model/tiền xử lý, không chứng minh model nhận đúng gậy.

Kết quả adapter OpenCV với ngưỡng confidence **0,35**, NMS **0,45**, ghép IoU **0,5** trên box crop AI:

| Tập | Số ảnh / box gậy | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|---|
| Validation crop | 18 / 6 | 1 | 2 | 5 | 0,3333 | 0,1667 |
| Diagnostic crop (test đã xem khi debug) | 16 / 4 | 0 | 1 | 4 | 0 | 0 |

Các P/R này dùng một ngưỡng cố định; không đồng nhất với ngưỡng do thư viện chọn khi tính thống kê validation. Sau khi dùng test để phát hiện lỗi bản đầu và debug, không còn xem nó là holdout độc lập bất biến.

Chạy trực tiếp trên đoạn `cam2_03.mp4` từ giây 168–192: **94 frame được lấy mẫu khoảng 3,90 FPS, 0 frame có detection gậy** ở ngưỡng 0,35. Video thực có gậy; đây là bỏ sót, không phải bằng chứng cảnh không có gậy. Thử các crop toàn cảnh chồng lấn cũng không ghép được với 28 box gậy đã chọn ở IoU 0,5, nên không thêm suy luận chia vùng vào runtime.

Artifact chẩn đoán riêng:

- `data/datasets/cue_bootstrap_20261120/diagnostic_v2/cue_preview.mp4`: video có overlay và ghi rõ thử nghiệm; không chèn box nhãn tay làm detection.
- `data/datasets/cue_bootstrap_20261120/diagnostic_v2/runtime_report.json`: predictions và tham số thật của crop/video.
- `data/datasets/cue_bootstrap_20261120/box_review_1.jpg` đến `box_review_3.jpg`: bảng đối chiếu box AI để người kiểm tra.
- `data/datasets/cue_bootstrap_20261120/artifact_checks.json`: hash model và kiểm tra CRC/nội dung sáu zip nhãn (36, 36, 12, 12, 12, 12 clip).

Cần thêm box gậy đã được người rà soát trên nhiều khoảng cách, góc gậy, ánh sáng và video mới trước khi huấn luyện/đánh giá lại. Chưa có bộ ground truth toàn khung hình để đo recall thực địa; 13 đề xuất WALKING mới phục vụ model hành động, không khắc phục thiếu nhãn box gậy.

Đây là bootstrap nhỏ, nhãn AI chưa được người kiểm tra và tập test chỉ có bốn crop dương. Chỉ số trên crop này không đại diện độ chính xác toàn cảnh, camera mới, theo dõi người hay hành động. Chưa nghiệm thu tại quán và chưa đủ điều kiện tự động tính tiền.

## Luồng runtime và kiểm thử

Detector chỉ nhận output YOLOv8 một lớp `(1, 5, N)`; COCO/pose không được diễn giải thành gậy. Gậy đã nạp chạy khi có người và hiện box `Gay thu nghiem`. Box chưa kiểm chứng bị lọc trước mapper, `validated=false` vẫn giữ nguyên. Xem ADR 0002.

Đã kiểm tra hồi quy đọc output, hoàn nguyên letterbox, loại output sai lớp, chặn gậy thử nghiệm khỏi mapper, lấy mẫu đi lại, tạo gói thiếu phiếu và ngăn gộp nhãn khác batch.

- `.venv/Scripts/python -m pytest`: **128 passed**, một warning Starlette/httpx có sẵn.
- `npm test` trong `apps/web`: **11 passed**.
- `npm run build` trong `apps/web`: **PASS**.
- `scripts/smoke.py` sau build, database tạm: **PASS**; Windows dùng `PYTHONUTF8=1` cho process con, `CAMERA_ENABLED=false`.
- `git diff --check`: **PASS**; weights, metadata, nhãn và dữ liệu riêng đều được gitignore.

Smoke kiểm tra web/API/FSM/billing bằng mô phỏng, không chứng minh thị giác. Đã chạy ONNX trực tiếp trên video thật; chưa nghiệm thu camera trực tiếp, chưa đo khả năng nhận diện gậy tin cậy hoặc vận hành tính tiền.
