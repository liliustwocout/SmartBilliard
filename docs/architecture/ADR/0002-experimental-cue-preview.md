# ADR 0002 — nhận diện gậy thử nghiệm và bằng chứng quyết định bàn

Trạng thái: chấp nhận cho thử nghiệm local. Ngày: 20/11/2026.

Bối cảnh: gate `validated` trước đây chặn cả inference nên model đã nạp vẫn không thể vẽ box để kiểm tra. Một file ONNX nạp thành công không chứng minh gậy đã được kiểm chứng trên camera.

Quyết định: pipeline gọi detector gậy đã nạp khi có người và còn bàn cần xử lý. Box gậy được trả cho preview, ghi rõ thử nghiệm. Trước `TableZoneMapper`, mọi box gậy của detector chưa kiểm chứng bị lọc khỏi detections dùng tổng hợp bàn. FSM tiếp tục nhận `cue_detector_ready=false`; `YoloCueDetector.validated` vẫn trả false. Không thêm công tắc bỏ gate.

Huấn luyện dùng môi trường Python riêng, runtime giữ OpenCV DNN và ONNX một lớp. ONNX xuất FP32/opset 12, được nạp và chạy thử lại bằng runtime. Weights, dữ liệu, nhãn và artifacts huấn luyện chỉ lưu local, không kèm Git.

Hệ quả: có thể quan sát lỗi gậy mà không đưa bằng chứng đó vào quyết định mở bàn; một lần inference gậy làm tăng chi phí xử lý khi có người. Test hồi quy kiểm tra cả danh sách preview và danh sách chuyển cho mapper. Kiểm chứng model, chất lượng nhãn và precision/recall thực địa vẫn là cổng riêng, không được suy từ việc có box hay test logic chạy qua.
