# Kế hoạch nhận diện hành động: Hướng A trước, Hướng B làm đích

Nguồn ý tưởng: ghi chú đề xuất ba hướng (A: YOLO Pose + rule engine; B: YOLO Pose + ST-GCN/PoseC3D; C: video action recognition). Chọn **B làm đích, triển khai A trước** để dựng dữ liệu và logic chuẩn, rồi mới huấn luyện model hành động. Hướng C chỉ nghiên cứu sau, không nằm trong kế hoạch này.

Các tên framework và định dạng dữ liệu của MMAction2 nêu bên dưới lấy từ ghi chú đề xuất và hiểu biết chung, **chưa kiểm chứng với phiên bản cài đặt thực tế**. Cần đọc lại tài liệu đúng phiên bản trước khi viết script xuất dữ liệu (bước P3).

Quyết định đã chốt xem mục 5.

## 1. Nguyên tắc (giữ nguyên các quy tắc của dự án)

- Một dự đoán hành động đơn lẻ (ví dụ SHOOTING) **không bao giờ tự mở bàn**. Hành động chỉ là một bằng chứng trong FSM.
- Thiếu bằng chứng hoặc bằng chứng mâu thuẫn thì chuyển **UNCERTAIN** (hiển thị là "Chờ xác nhận" kèm lý do) để nhân viên quyết định.
- AI không tự đóng phiên từ việc người hoặc gậy biến mất. Chế độ "AI tự động" chỉ tự mở bàn.
- Số liệu phải đo được. Không hứa độ chính xác trước khi có kết quả trên dữ liệu độc lập.
- Code nghiệp vụ (FSM, quyết định) không phụ thuộc OpenCV, Ultralytics hay PyTorch. Huấn luyện làm trong môi trường riêng, runtime chỉ nạp ONNX.
- Dữ liệu người chơi, weights riêng và nhãn không commit (đã gitignore dưới `data/` và `models/`).

## 2. Hiện trạng trong repo

Hướng A đã có phần lớn nền tảng:

| Thành phần | Trạng thái |
|---|---|
| Phát hiện người + keypoint COCO-17 | Có: `YoloPoseDetector`, model `yolov8n-pose.onnx` đã nạp được |
| Tracking | Có: `ByteTracker` tự viết (`services/vision/tracker.py`) |
| Gán người vào bàn | Có, nhưng chỉ dựa vào **điểm chân** và vùng ROI (`mapper.py`) |
| Phân tích hành động theo luật | Có: `pose_analyzer.py` cho ra `PLAYING / NOT_PLAYING / UNKNOWN` từ tư thế cúi, gậy, chuyển động lau bàn |
| Quyết định theo thời gian | Có: `decision.py` (FSM, NEEDS_CONFIRMATION, cooldown, cảnh báo quên mở bàn) |
| Đánh giá trên video | Có: `scripts/evaluate_video.py` |
| Nhãn hành động theo từng người | **Chưa có** (chỉ có dataset khung hình gậy cho YOLO) |
| Xuất chuỗi keypoint theo `person_id` | **Chưa có** |
| Công cụ gán nhãn theo khoảng thời gian | **Chưa có** |
| Model hành động (ST-GCN/PoseC3D) | **Chưa có** |
| Chuyển động của bi, trạng thái POS trong quyết định | Phiên ACTIVE đã có (AI tạm dừng cho bàn đã mở); **chuyển động bi chưa có** |

Hai hạn chế quan sát được khi chạy thử, ảnh hưởng trực tiếp đến kế hoạch:
- **FPS xử lý thực tế chỉ khoảng 2 FPS** trên CPU (mục tiêu cấu hình là 8). Cửa sổ 2–4 giây khi đó chỉ có 4–8 khung, quá thưa cho model chuỗi. Cần cải thiện tốc độ suy luận trước hoặc song song với P4.
- Người cúi đánh có điểm chân lệch khỏi vùng đứng, nên việc gán bàn chỉ bằng điểm chân dễ sai (đã gặp khi chỉnh ROI).

## 2b. Kết quả P0 sơ bộ (18/11/2026, kiểm tra bằng mắt, chưa phải số liệu chính thức)

Chạy pipeline hiện tại (pose + ByteTracker + mapper + `pose_analyzer`, không có model gậy) trên hai video quán, lấy mẫu mỗi 8 khung (~2,5 mẫu/giây), ROI hiện hành gồm Bàn 1 và Bàn 2. Tổng cộng 2.998 mẫu theo từng bàn. **Chưa có nhãn của team**, nên đây chỉ là kiểm tra định tính do người đánh giá xem 18 khung hình ngẫu nhiên (6 khung mỗi nhóm), không phải precision/recall.

| Quan sát | Số liệu / ví dụ |
|---|---|
| Bàn 1 được đánh dấu PLAYING | 374/750 và 455/749 mẫu (khoảng 50–61%) |
| Bàn 2 (**bàn phủ vải, không chơi**) bị đánh dấu PLAYING | 130/750 và 128/749 mẫu (khoảng 17%) |
| Bàn 1 đổi trạng thái giữa hai mẫu liên tiếp | 183/750 và 144/749 lần (khoảng 19–24%), tức trạng thái nhấp nháy; FSM phải làm mượt |

Kiểm tra bằng mắt:
- **Dương tính giả ở Bàn 2:** 6/6 khung PLAYING được xem đều là người đứng hoặc dựa vào bàn phủ vải, không ai chơi. Nếu bật chế độ AI tự động mở bàn thì Bàn 2 có nguy cơ bị mở nhầm.
- **Bỏ sót ở Bàn 1:** trong 6 khung NOT_PLAYING có người, 2 khung có người đang cúi đánh ở đầu bàn bên phải nhưng bị gắn `SPECTATOR_OR_CLEANING`.
- Các khung PLAYING ở Bàn 1 được xem phần lớn là hợp lý (có người cầm gậy cúi đánh), nhưng chưa có nhãn nên chưa kết luận được tỉ lệ đúng.

Kết luận tạm thời: luật tư thế hiện tại **sai theo cả hai hướng** (dựa/đứng gần bàn bị tính là chơi; cúi đánh ở đầu bàn bị bỏ sót). Đây là lý do cần dữ liệu có nhãn và model hành động, và cần làm P1 (gán người vào bàn, luật hành động) trước khi bật chế độ AI tự động ở bất kỳ bàn nào. Trong lúc chưa sửa, nên tắt theo dõi bàn không chơi (bàn phủ vải) bằng công tắc `enabled` đã có trong kế hoạch nhiều bàn.

## 3. Các giai đoạn

### P0. Đo baseline Hướng A (làm trước, chưa viết model mới)
- Chọn tập clip kiểm thử cố định từ các video quán đã quay, có cả cảnh che khuất, thiếu sáng, nhiều người.
- Gán nhãn tay tối thiểu theo khoảng thời gian và người (xem định dạng ở P2) cho tập này.
- Chạy pipeline hiện tại, đo: tỉ lệ đúng/sai của PLAYING so với nhãn tay, số lần mở nhầm, số lần bỏ sót, các ca lỗi điển hình.
- **Điều kiện qua cổng:** có bảng số liệu và danh sách ca lỗi. Kết quả này quyết định mức cần thiết của B. Nếu A đã đủ cho nhu cầu quán thì B hạ ưu tiên.

### P1. Hoàn thiện Hướng A
- **Gán người vào bàn tốt hơn:** thêm hông, hướng thân người và khoảng cách tới mép bàn, không chỉ điểm chân. Người đứng giữa hai bàn cần có quan hệ không gian rõ ràng, không dùng tỉ lệ giao nhau của bounding box.
- **Nhãn hành động rule-based chi tiết hơn:** tách `AIMING/SHOOTING` (cúi, gậy) khỏi `WALKING` (di chuyển), `WATCHING` (đứng yên, không cúi), còn lại `UNKNOWN`. `CLEANING` và `RACKING` chỉ giữ nếu rule đủ tin cậy; nếu không thì chờ B.
- **Ghi log keypoint theo người, tùy chọn bật** (cục bộ, không lưu ảnh) để phục vụ P3.
- Test hồi quy cho từng rule và cho gán bàn.

### P2. Thu thập và gán nhãn
- Bốn nhãn khởi đầu: `SHOOTING, AIMING, WATCHING, WALKING`. `CLEANING` và `RACKING` thêm sau.
- Định dạng nhãn: `video, track_id, t_start, t_end, label` (CSV hoặc JSON), gán theo khoảng thời gian và theo người thực hiện.
- Công cụ gán nhãn: **gói offline** (xem `docs/ai/LABELING_GUIDE.md`), nhiều người cùng gán, **đã có**: `scripts/build_label_pack.py` (tạo clip, làm mờ mặt), `tools/label_pack/template.html` (trang gán nhãn), `scripts/merge_labels.py` (gộp, đo đồng thuận). Mỗi nhãn ghi kèm tên người gán, để đo mức đồng thuận và xử lý bất đồng. Người xem nhận một clip theo từng người (`track_id`) và chọn nhãn cho từng khoảng thời gian.
- Thu thập nhiều ca: ban ngày/tối, ít/nhiều người, bàn khác nhau, góc che khuất. Một góc camera duy nhất sẽ làm model học thuộc bối cảnh; đây là rủi ro lớn nhất.
- Quyền riêng tư: chỉ lưu keypoint và nhãn khi huấn luyện, không đưa ảnh có mặt người vào repo; cần sự đồng ý của quán và người chơi khi ghi hình.

### P3. Trích keypoint và tạo dataset
- Script `extract_skeletons`: video → keypoint theo `track_id` → cửa sổ trượt 2–4 giây ở FPS cố định, chuẩn hóa tọa độ theo thân người.
- Xuất theo định dạng MMAction2 cho skeleton (đọc lại tài liệu dataset tùy chỉnh đúng phiên bản) kèm bản `.npz` đơn giản để thử model nhẹ.
- **Chia train/val/test theo video hoặc phiên quay**, không chia theo khung hay cửa sổ, vì các đoạn liền kề gần như giống nhau. `extract_frames.py` hiện đã có logic chia split theo video, tái sử dụng được.

### P4. Huấn luyện offline và chọn model
- Môi trường riêng (không cài PyTorch hay MMAction2 vào `.venv` của dự án, vì đã gặp xung đột opencv khi cài ultralytics).
- So sánh theo thứ tự tăng độ phức tạp: baseline nhẹ (1D-CNN/GRU trên keypoint) → ST-GCN → PoseC3D. Dừng ở mô hình đơn giản nhất đủ đạt ngưỡng.
- Chỉ số: macro-F1, ma trận nhầm lẫn theo nhãn, kết quả riêng cho cặp khó như `CLEANING` / `RACKING` / `WATCHING`; đo trên phiên quay độc lập.
- Xuất ONNX và kiểm tra có chạy được trong runtime hay không (xem mục 5 về `onnxruntime`).
- Pretrained không hiểu hành động đặc thù như xếp bi hay lau bàn, nên chất lượng phụ thuộc hoàn toàn dữ liệu riêng của quán.

### P5. Tích hợp runtime
- Module `action_classifier` đặt sau tracker: giữ buffer keypoint theo `track_id`, suy luận theo chu kỳ, trả nhãn và độ tin cậy vào `PersonAnalysis`.
- Thiếu model hoặc độ tin cậy thấp thì **rơi về rule của P1**, không dừng hệ thống.
- Ngưỡng nằm trong cấu hình và kiểm tra khi khởi động; hiện thêm trạng thái model trong `GET /api/camera/status`.
- Giữ cơ chế tạm dừng AI cho bàn đang có phiên để tiết kiệm tài nguyên.

### P6. Hợp nhất theo bàn và trạng thái UNCERTAIN
- Tổng hợp chuỗi hành động theo từng bàn trong cửa sổ thời gian (bỏ phiếu có trọng số theo độ tin cậy), không dựa vào một khung.
- Thêm bằng chứng phụ: chuyển động của bi trong vùng mặt nỉ (cần thử nghiệm xem đủ ổn định không) và trạng thái phiên trong POS.
- Quy tắc ví dụ: `SHOOTING/AIMING` liên tục + bi di chuyển → đủ bằng chứng; `SHOOTING` nhưng không có người ở vùng đứng, hoặc có cả `CLEANING` lẫn `AIMING` → `UNCERTAIN`.
- Quy ước nhãn → bằng chứng: `SHOOTING/AIMING` là bằng chứng chơi; `WATCHING/WALKING/CLEANING/RACKING` không phải bằng chứng chơi. `RACKING` có thể báo hiệu sắp chơi nhưng không được dùng để mở bàn.
- Hiển thị lý do `UNCERTAIN` trên banner xác nhận. Test hồi quy FSM cho từng tổ hợp mâu thuẫn.

### P7. Đánh giá và bàn giao
- Bảng số liệu cuối trên tập độc lập, nêu rõ cái gì chưa kiểm chứng.
- ADR cho quyết định kiến trúc (runtime ONNX, tách môi trường huấn luyện); cập nhật README, API_SPEC, MODEL_STRATEGY, EVALUATION_METRICS.
- Trước bàn giao: `pytest`, `npm test`, `npm run build`, và `scripts/smoke.py` khi đổi luồng tích hợp.

## 4. Rủi ro

| Rủi ro | Hướng xử lý |
|---|---|
| Dữ liệu quá ít (hiện chỉ có hai video quán khoảng 5 phút mỗi video) | P0 xác định khoảng trống trước; chưa hứa số lượng. Thu thêm nhiều ca trước khi huấn luyện ST-GCN. |
| Học thuộc bối cảnh một camera | Chia theo phiên quay; thu thêm góc và điều kiện sáng; báo cáo kết quả riêng theo phiên. |
| FPS thấp làm chuỗi keypoint thưa | Tối ưu suy luận (model nhỏ hơn, GPU, chỉ chạy bàn chưa mở) trước khi huấn luyện model chuỗi. |
| Nhãn không nhất quán, nhất là `CLEANING` / `RACKING` / `WATCHING` | Quy tắc gán nhãn viết rõ, hai người gán độc lập một phần để đo mức đồng thuận. |
| Người bị che khuất, ID tracker bị đổi | Đo ID switch ở P0; cửa sổ ngắn và bỏ phiếu để chịu lỗi. |
| Thêm phụ thuộc nặng vào runtime | Chỉ nạp ONNX; huấn luyện ở môi trường riêng. |

## 5. Quyết định

**Đã chốt:**
- **Cách gán nhãn: gói gán nhãn offline** (cách A). Nhóm 4 người ở xa nhau, không cùng mạng, nên không dùng máy chủ LAN hay deploy (app chưa có đăng nhập, video là hình ảnh khách). Mỗi người nhận một file zip, mở `index.html` bằng trình duyệt, gán nhãn rồi gửi lại một file kết quả; người phụ trách gộp bằng `scripts/merge_labels.py`.
- **Nhiều camera:** video đến từ nhiều camera khác nhau. Mỗi nguồn được gắn `camera_id`; chia train/val/test nên **chừa nguyên một camera hoặc một phiên quay** làm tập kiểm tra để đo khả năng tổng quát hóa sang góc quay mới. ROI chỉ cần cho phần gán bàn, không cần cho việc gán nhãn hành động từng người.
- **Mỗi clip do 2 người gán độc lập** để đo mức đồng thuận (kappa), công việc chia đều cho 4 người.
- **Công cụ gán nhãn:** màn gán nhãn nằm trong app, nhiều thành viên trong team cùng gán được (cách cùng làm xem mục P2 và câu hỏi còn mở bên dưới).
- **Nhãn khởi đầu: 4 nhãn** `SHOOTING, AIMING, WATCHING, WALKING`. `CLEANING` và `RACKING` để sau, khi 4 nhãn đầu đã đạt ngưỡng.
- **Nguồn dữ liệu:** video quay tại quán nhà của người dùng; thành viên trong team gán nhãn.
- **Phần cứng huấn luyện:** có GPU, nên có thể thử ST-GCN/PoseC3D mà không bị giới hạn bởi CPU.

**Còn mở:**
1. **Runtime model hành động:** thử `cv2.dnn` (đã có sẵn) trước; nếu graph không chạy được thì thêm `onnxruntime`.
2. **Đồng ý ghi hình:** quán đã biết và đồng ý việc ghi hình khách để làm dữ liệu huấn luyện chưa; cách xử lý khuôn mặt trong clip dùng để gán nhãn.

## 6. Ngoài phạm vi
- Hướng C (nhận diện hành động trực tiếp từ chuỗi RGB).
- Nhiều camera.
- Thanh toán thật hoặc tự động đóng phiên.
