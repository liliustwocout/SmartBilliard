# Hướng dẫn gán nhãn hành động

Dành cho thành viên nhóm gán nhãn (không cần biết lập trình) và người phụ trách tạo gói.

## 1. Cho thành viên gán nhãn

1. Nhận file `pack_member-N.zip` từ người phụ trách. **Chỉ dùng trong nhóm, không đăng hay chuyển tiếp ra ngoài.**
2. Giải nén, mở file `index.html` bằng trình duyệt (Chrome, Edge hoặc Firefox). Không cần cài đặt hay có mạng.
3. Nhập tên của bạn, bấm **Bắt đầu**.
4. Mỗi clip dài khoảng 3 giây, chỉ nhìn **người có khung màu xanh lơ**. Chọn nhãn rồi tự sang clip tiếp. Phím tắt: 1–6 chọn nhãn, Cách để dừng/phát, ← quay lại.
5. Bấm **Lưu kết quả (tải file)** thường xuyên. Khi xong, gửi file `ket-qua-....json` cho người phụ trách. Muốn làm tiếp lần sau thì mở lại `index.html` (trình duyệt thường nhớ tiến độ; nếu không, dùng nút nạp file tiến độ cũ ở màn đầu).

### Bốn nhãn chính
| Nhãn | Khi nào chọn |
|---|---|
| **Đang đánh** (SHOOTING) | Đang thực hiện cú đánh, gậy đẩy về phía bi. |
| **Đang ngắm** (AIMING) | Cúi người, đặt gậy lên tay cầu để chuẩn bị đánh, chưa đẩy gậy. |
| **Đứng xem** (WATCHING) | Đứng hoặc ngồi xem, không chuẩn bị đánh. Cầm gậy đứng chờ lượt cũng là xem. |
| **Đi lại** (WALKING) | Đang di chuyển, không đứng yên ở bàn. |

Hai nhãn phụ: **Không chắc** (khó quyết định, đừng đoán) và **Clip lỗi** (khung không đúng một người, hoặc người được đánh dấu liên tục thay đổi).

Cả nhóm cần thống nhất định nghĩa trên trước khi bắt đầu. Nếu gặp tình huống khó (ví dụ đang chờ lượt nhưng cúi nhìn bi), bàn với nhau một quy tắc chung rồi ghi lại.

## 2. Cho người phụ trách

### Tạo gói (mỗi camera một `--source`)
```powershell
.\.venv\Scripts\python.exe scripts/build_label_pack.py `
  --source cam-a=D:\video\camera_a `
  --source cam-b=D:\video\camera_b `
  --members 4 --redundancy 2 --max-clips 400
```
- Video từ nhiều camera: lặp `--source TÊN_CAM=đường_dẫn` (một file hoặc cả thư mục). Số clip chia đều giữa các camera.
- Mỗi clip được **2 người** gán độc lập (`--redundancy 2`) để đo mức đồng thuận; công việc chia đều cho 4 người.
- Cần `models/yolov8n-pose.onnx` (xem `models/README.md`). Mặc định thử GPU nếu OpenCV hỗ trợ, thêm `--cpu` để ép CPU.
- Kết quả nằm trong `data/label_packs/batch-.../`: gửi cho từng người **chỉ** file `pack_member-N.zip`. Không gửi `clips_index.json` hay `_sprites/` (có tên video, camera và thời điểm).
- Khuôn mặt của mọi người phát hiện được trong clip đều được làm mờ. Người ở xa không được phát hiện có thể vẫn lộ mặt, nên chỉ chia sẻ trong nhóm.

### Gộp kết quả
Đặt các file `ket-qua-*.json` vào một thư mục, rồi:
```powershell
.\.venv\Scripts\python.exe scripts/merge_labels.py data\label_packs\batch-...\results\*.json
```
- Sinh `labels_final.jsonl` (clip có nhãn AGREED hoặc MAJORITY) và `agreement_report.json` (đồng thuận từng cặp, kappa, phân bố nhãn, danh sách clip cần xem lại).
- Chỉ bốn nhãn chính được tính là phiếu. `Không chắc` và `Clip lỗi` không bao giờ thành nhãn cuối.
- Clip hòa phiếu (REVIEW) cần cả nhóm xem lại. Kappa thấp nghĩa là định nghĩa nhãn chưa rõ, nên thống nhất lại trước khi gán thêm.

### Rà soát clip thiếu phiếu, ưu tiên WALKING

`INSUFFICIENT` nghĩa là chưa đủ **phiếu hợp lệ**, kể cả khi hai thành viên đều chọn `INVALID`. Không đổi clip xe máy, khung bám sai người hoặc đổi ID thành một trong bốn nhãn để làm đủ số lượng. Hành động xếp bi/làm việc khác không thuộc bốn lớp thì chọn `UNSURE`.

```powershell
.\.venv\Scripts\python.exe scripts/build_review_pack.py data/label_packs/BATCH `
  --results "data/label_packs/BATCH/ketqua/*.json" `
  --out data/label_packs/BATCH/review-moi --members 2
```

Mỗi người nhận một gói có tất cả clip chưa chốt, kể cả clip chưa có phiếu nào; tên video/camera và nhãn gợi ý không đưa vào gói. Thư mục đích phải mới để tránh ghi đè lần rà soát trước. Hai người trả kết quả rồi gộp **cùng các phiếu cũ của đúng batch đó**; không gộp khác batch. Wildcard file kết quả được mở rộng trong Python nên dùng được trên Windows.

Lấy thêm clip đi lại từ đoạn video chưa nằm trong batch trước:

```powershell
.\.venv\Scripts\python.exe scripts/build_label_pack.py --source cam-a=PATH `
  --focus walking --exclude-index data/label_packs/BATCH/clips_index.json `
  --members 4 --redundancy 2 --max-clips 48
```

Điểm `walking_score` xếp hạng dịch chuyển, giảm ảnh hưởng rung box và bỏ bước nhảy lớn có thể là đổi ID. Nó không xác nhận có người thật, không phân loại hành động và vẫn có thể chọn nhầm. Số clip xuất có thể ít hơn `--max-clips`.

Kết quả AI rà soát nằm riêng dưới `ai_review_*/`, định dạng `smartbilliard-ai-review-v1`, có lý do và `human_review_required=true`. Chúng không phải phiếu độc lập của thành viên và không tự đưa vào `merged/labels_final.jsonl`. Không cộng nhãn AI vào kappa của nhóm.

### Chốt nhãn cho huấn luyện thử nghiệm sau khi AI rà soát

Khi giao AI làm tiếp phần rà soát, dùng bản chốt `smartbilliard-adjudication-v1`, ghi `reviewer_type=AI` và lý do từng clip. `ACCEPT` chỉ nhận bốn nhãn chính; `EXCLUDE` dùng `INVALID` hoặc `UNSURE` để loại clip lỗi, ngoài bốn lớp hoặc không đủ bằng chứng. Loại clip là một kết quả rà soát hoàn tất, không ép nó thành nhãn hành động.

```powershell
.\.venv\Scripts\python.exe scripts/finalize_label_review.py data/label_packs/BATCH `
  --review PATH/adjudication.json --out data/label_packs/NEW_REVIEWED_OUTPUT
```

Script giữ nguyên phiếu và nhãn đồng thuận cũ; đầu ra phải là thư mục mới. Bản chốt phải phủ đủ các clip chưa có nhãn đồng thuận, không có ID lạ/trùng. Nhãn AI mang `status=AI_ADJUDICATED`, không thêm người gán nhãn giả hoặc thay số liệu kappa. Nếu clip lẫn hành động, có thể giữ một đoạn rõ ràng dài ít nhất hai giây bằng `sample_start`/`sample_stop` (chỉ số đầu vào, stop không bao gồm); script cắt đồng bộ frame, box và keypoint, tính lại thời gian video.

Đầu ra gồm `labels_reviewed.jsonl`, `excluded.jsonl`, `clips_index.json` và manifest/hash nguồn. Đây là nhãn đã được AI chốt cho thử nghiệm local, không phải xác nhận của hai người hoặc nghiệm thu camera. Xem [lượt rà soát ngày 21/11](LABEL_REVIEW_20261121.md) và dataset đã xuất từ các nhãn này.

## 3. Quyền riêng tư
- Dữ liệu quay khách của quán: cần sự đồng ý của quán và khách về việc dùng hình ảnh để làm dữ liệu huấn luyện.
- `data/label_packs/` đã được gitignore; không commit clip, gói hay nhãn.
- Chỉ chia sẻ gói trong nhóm.
