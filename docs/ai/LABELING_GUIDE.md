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

## 3. Quyền riêng tư
- Dữ liệu quay khách của quán: cần sự đồng ý của quán và khách về việc dùng hình ảnh để làm dữ liệu huấn luyện.
- `data/label_packs/` đã được gitignore; không commit clip, gói hay nhãn.
- Chỉ chia sẻ gói trong nhóm.
