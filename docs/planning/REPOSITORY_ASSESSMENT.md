# Phase 0 — kiểm tra repository (08/11/2026)

Đường dẫn làm việc: `G:\Project\PSI_2026`.

- Ban đầu chỉ có `AGENTS.md` rỗng (0 byte) và `docs/references/HỒ SƠ ĐĂNG KÝ PSI2026 - BM02.docx.txt`.
- Không có `.git`, code, manifest, lockfile, test hoặc ứng dụng đang chạy. Không có code để tái sử dụng.
- Giữ nguyên hồ sơ tham khảo, dùng tên nhóm và bối cảnh sản phẩm. Không sao chép thông tin cá nhân vào ứng dụng/test.
- Python 3.11.9, Node 22.17.0, npm 11.12.1 được tìm thấy. Tạo virtualenv riêng; không thay đổi môi trường Python toàn máy.

## Rủi ro và quyết định

Hồ sơ gốc mô tả định hướng edge/cloud, nhiều luồng camera và Loyalty; master prompt mới chỉ định MVP local 1 camera. Theo phạm vi mới, chưa thực hiện cloud, F&B, Loyalty hay edge box riêng. Các thông số phần cứng trong hồ sơ là mục tiêu, không phải kết quả đo.

Thiếu camera/video mẫu, dataset và cue weights; không thể xác nhận chất lượng AI. Phase 2 kiểm chứng tích hợp qua sự kiện nhân tạo. Kiểm chứng video thật cần milestone sau. Bàn mini có thể chỉ thấy tay, cần pipeline riêng.

Giữ monorepo đã yêu cầu, không tạo thư mục `infra/` rỗng vì chưa có hạ tầng cần quản lý. `data/` có hướng dẫn và database runtime bị ignore. Không khởi tạo Git hoặc publish khi chưa được yêu cầu.
