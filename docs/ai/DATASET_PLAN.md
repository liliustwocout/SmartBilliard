# Kế hoạch dữ liệu

Chưa có camera/video/dataset gán nhãn trong repository. Unit fixtures là dữ liệu nhân tạo cho logic, không phải bộ đánh giá thị giác.

## Thu thập và cấu trúc dự kiến

Đức xin phép chủ quán/người xuất hiện; Sơn ghi clip ngắn đủ 15 tình huống, nhiều ánh sáng, bàn gần/xa, occlusion và người đi ngang. Ghi camera/resolution/FPS, vị trí, table_id và mode REAL_CLUB/MINI_TABLE. Thu cả negative không ai chơi nhưng có người đứng gần.

`data/datasets/<dataset-id>/manifest.json` dự kiến chứa clip ID, consent reference, mode, camera/setup hash, split, annotation path và retention deadline. Ảnh/video và nhãn chứa người không commit Git. Test fixtures nhỏ chỉ dùng khi có quyền rõ ràng.

## Nhãn

Person/hand/cue boxes riêng; track IDs trong clip; ground-truth table assignment/ambiguous/outside; thời điểm bắt đầu chơi do hai người thống nhất; cue visibility/occlusion. Cue dataset theo YOLO: images/train,val,test; labels cùng tên, một dòng `class cx cy w h` chuẩn hóa; dataset.yaml có names: cue. Kèm hard negatives.

Split theo clip/quán/ngày quay, không chia các frame liền nhau ngẫu nhiên giữa train/test. Dành holdout chưa dùng chỉnh threshold; kiểm tra agreement khi gán zone/start.

## Quyền riêng tư

Không thu khuôn mặt/định danh nếu không cần; giới hạn góc quay, mã hóa lưu trữ nếu cần, chia sẻ trong nhóm được phép, xóa theo retention đã thống nhất. Không upload dịch vụ AI/cloud mặc định. Kết quả báo cáo dùng aggregate và clip minh họa được duyệt.
