# PRD — SmartBilliard MVP

## Vấn đề và người dùng

Nhân viên quán cần biết bàn nào đã sử dụng, mở phiên đúng một lần và chốt tiền có thể đối soát. Đạt/An/Sơn/Đức cần trình diễn luồng có bằng chứng tại PSI2026. Chủ quán là người đánh giá giá trị nghiệp vụ; chưa có khảo sát định lượng trong repository.

## Mục tiêu

MVP đầy đủ sau validation: 1 camera, 3–4 bàn, person/tracking/ROI → quyết định thời gian → xác nhận hoặc tự mở demo → dashboard realtime → checkout → lịch sử. Camera 7–8 bàn và 4K là giả thuyết đo riêng.

Phase 2 bàn giao trước: thay đầu vào camera bằng mô phỏng ghi nhãn, giữ nghiệp vụ và lưu trữ thật. Mặc định PERSON_ONLY yêu cầu nhân viên xác nhận. Mất người không chốt bàn.

## Yêu cầu

- Mỗi bàn tối đa một ACTIVE; retry không mở hoặc checkout nhầm phiên mới.
- Backend lưu UTC, snapshot giá, VND số nguyên và quyết định số tiền.
- Bốn bàn mặc định, cấu hình lên tám, dashboard tiếng Việt tối, cảnh báo mất kết nối.
- REAL_CLUB dùng người thật; MINI_TABLE cần hand adapter nếu không thấy toàn thân. Không đánh đồng kết quả.
- Local offline sau cài dependency/build; không lưu ảnh cá nhân không cần thiết.

## Thành công

Phase 2 đạt khi API/test/smoke chứng minh tích hợp, default không tự tính tiền và UI nhận snapshot thật. Thành công AI chỉ công bố sau video/camera evaluation được gán nhãn. Không dùng test nhân tạo để tuyên bố accuracy.

Không làm ngay: POS/F&B, tồn kho, Loyalty, đa chi nhánh, phân tích cloud, nhận diện danh tính hoặc thanh toán ngân hàng.
