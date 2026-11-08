# Chiến lược model

## Person

Phase 3 đánh giá YOLO pretrained nhỏ trước để hợp laptop; lựa chọn cụ thể dựa video và license. Chỉ class person cho REAL_CLUB. Lưu weights tại máy trước demo; ghi tên/version/hash, input size, confidence, device và tracker config. Chưa cài hoặc tải model trong Phase 2.

## Cue

COCO pretrained không có class billiard cue chuyên biệt. `CueDetector` nhận frame và trả detections; custom weights cần label cue thống nhất, holdout và kiểm thử gắn đúng bàn. Không bật readiness chỉ vì file weights tồn tại.

Fine-tune dự kiến: thu ảnh có/không cue, tay/viền bàn/đường đèn làm hard negatives; gán box cue; split theo video/quán; dùng Ultralytics detect train với dataset YAML local và pretrained checkpoint phù hợp; lưu config/seed/weights/hash; evaluate holdout theo gần/xa/che khuất. Chỉ bật gate sau khi đạt tiêu chí nhóm chốt trước đánh giá. Đây là hướng dẫn kế hoạch, chưa có dataset hoặc lệnh train đã chạy.

OpenCV line/Hough có thể làm baseline experimental, nhưng viền bàn/gậy/đèn đều sinh đường thẳng; không dùng nó để tuyên bố cue detection đã tin cậy. Pose/wrist association chỉ cân nhắc khi resolution đủ.

## MINI_TABLE

Nếu camera chỉ thấy tay, chọn hand detector được kiểm chứng riêng. Hand presence không tương đương person presence. Ghi mode vào experiment/evidence; không cộng metric hai mode. Mọi model option phải được benchmark local/offline trước khi dùng sân khấu.
