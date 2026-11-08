# Đo chất lượng AI và vận hành

Chưa có số liệu camera; không đưa giá trị giả vào pitch hoặc dashboard.

- Person/cue precision = TP/(TP+FP), recall = TP/(TP+FN); ghi IoU threshold, confidence, matcher, dataset split và count. Cue không đánh giá nếu chưa có detector.
- Table assignment accuracy = số assignment đúng / số mẫu ground truth có thể gán; báo riêng ambiguity/outside thay vì loại chúng để làm đẹp kết quả.
- False auto-open: số phiên tự mở sai / số giờ-bàn quan sát (kèm tổng số mở và chính sách). Missed opening: số lần bắt đầu thật không được phát hiện trong cửa sổ định trước / tổng lần bắt đầu thật.
- Latency: capture/observation, backend commit, WS nhận và UI render; báo p50/p95 trên cùng clock hoặc độ lệch clock được đo. HTTP smoke không đo capture-to-dashboard latency.
- Processing FPS, dropped frames, capture age, CPU/RAM và GPU nếu có; ghi warmup, thời lượng, hardware, model/input size, camera resolution và số ROI.
- Chia kết quả near/far, table_id, lighting, occlusion, REAL_CLUB/MINI_TABLE. Không tổng hợp tay mini thành bằng chứng person thật.

Khi chưa có mẫu hoặc mẫu số=0, ghi N/A, không ghi 100%. Chốt tiêu chí chấp nhận trước holdout; default giữ staff confirmation nếu evidence chưa đủ. Tám bàn/4K là một experiment riêng sau bốn bàn.
