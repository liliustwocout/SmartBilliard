# Kế hoạch tổ chức lại giao diện web

**Trạng thái: đã thực hiện** (tab Tổng quan chỉ còn lưới bàn và banner cảnh báo; tab Thử nghiệm, Hệ thống & camera đã tách thành `apps/web/src/views/`). Bổ sung ngoài kế hoạch gốc: banner "AI phát hiện đang đánh" với nút Xem camera / Xác nhận mở, tạm dừng AI cho bàn đã mở, chỉnh cấu hình trực tiếp và chế độ mở bàn (Người duyệt / AI tự động) ở trang Hệ thống & camera.

Phạm vi: chỉ frontend (`apps/web/src`). Không đổi backend, API hay logic nghiệp vụ.

## 1. Vấn đề hiện tại

Tab **Tổng quan bàn** chứa quá nhiều thứ không liên quan đến việc xem bàn:

- Banner chế độ demo dài.
- Dải 4 chỉ số (bàn đang chơi, tiền đang chạy, doanh thu đã chốt, chờ xác nhận). Dải này nằm ngoài khối `tab === 'dashboard'` nên hiện ở mọi tab.
- Cột phải gồm: panel tự động hóa video, bộ phát mô phỏng (kèm nút bật/dừng camera và ảnh camera nhỏ), nhật ký tín hiệu.
- Phần chi tiết bàn nằm dưới lưới bàn, đẩy nội dung xuống.
- `App.tsx` dài hơn 300 dòng, JSX rất dài, khó bảo trì.

## 2. Cấu trúc đích

| Tab | Nội dung |
|---|---|
| **Tổng quan bàn** | Chỉ banner cảnh báo quên mở bàn (khi có) và lưới thẻ bàn. |
| **Camera trực tiếp** | Giữ nguyên, thêm panel tự động hóa video. |
| **Thử nghiệm** (mới) | Bộ phát mô phỏng, bật/dừng camera, ảnh camera nhỏ, nhật ký tín hiệu theo bàn, panel video/đánh giá, banner chế độ mô phỏng. |
| **Lịch sử phiên** | Giữ nguyên; hiển thị thêm doanh thu đã chốt. |
| **Hiệu chuẩn ROI** | Giữ nguyên. |
| **Hệ thống & camera** | Giữ nguyên, thêm dải 4 chỉ số ở đầu trang. |

### Quyết định đã chốt

1. **Bốn chỉ số**: bỏ khỏi Tổng quan, chuyển sang tab Hệ thống (doanh thu đã chốt cũng hiện ở Lịch sử, cùng nguồn dữ liệu).
2. **Chi tiết bàn**: mở rộng ngay trong thẻ bàn. Bấm thẻ thì bung ra, chỉ mở một thẻ tại một thời điểm.
3. **Banner chế độ** (CAMERA LIVE / VIDEO LIVE / THỦ CÔNG / MÔ PHỎNG): thu thành badge nhỏ ở topbar; banner dài chỉ còn ở tab Thử nghiệm.

## 3. Tổng quan bàn sau khi sửa

- Banner cảnh báo quên mở bàn (giữ, vì nhân viên cần thấy ngay) với nút Mở bàn / Tính bù giờ AI.
- Lưới thẻ 3–4 cột trên màn rộng, 2 cột trung bình, 1 cột trên mobile.
- Thẻ bàn: tên, trạng thái, badge AI, hình bàn, thời gian, tiền, đơn giá, nút Mở bàn / Xác nhận mở / Thanh toán.
- Phần mở rộng trong thẻ: bắt đầu phiên, nguồn mở bàn, quy tắc tính tiền, ghi chú cooldown/tín hiệu cũ.

## 4. Các bước thực hiện

1. Tách `App.tsx` thành các view: `TablesView`, `LabView`, `LiveView`, `HistoryView`, `SystemView`. Giữ nguyên state và logic; chỉ di chuyển JSX.
2. Thêm tab "Thử nghiệm" vào điều hướng; chuyển các khối từ cột phải sang đó. Thêm bộ chọn bàn cho nhật ký tín hiệu.
3. Rút gọn Tổng quan như mục 3. Chuyển dải chỉ số sang Hệ thống. Sửa lỗi dải này hiện ở mọi tab.
4. Chỉnh CSS: lưới bàn nhiều cột, thẻ mở rộng, badge chế độ ở topbar. Dọn style inline còn sót ở khối Camera trực tiếp.
5. Kiểm tra: `npm test`, `npm run build`, mở trình duyệt chụp ảnh từng tab (Tổng quan, Camera, Thử nghiệm, Lịch sử, ROI, Hệ thống) ở màn rộng và mobile.

## 5. Rủi ro và lưu ý

- Vòng lặp mô phỏng (`simulating`) và `lastEvent` đang nằm trong `App`. Khi tách view phải giữ state ở `App` hoặc một hook chung, để chuyển tab không làm mất hoặc dừng mô phỏng ngoài ý muốn.
- Ảnh camera nhỏ dùng `/api/camera/stream`. Chỉ render ảnh trong tab cần dùng để tránh giữ kết nối stream khi không xem.
- Không gọi mô phỏng là camera AI; nhãn "Thử nghiệm" phải nói rõ đây là dữ liệu nhân tạo.
- Không hardcode số liệu hiển thị; mọi số lấy từ snapshot backend như hiện tại.

## 6. Ngoài phạm vi

- Backend, API, schema, `API_SPEC`.
- Thay đổi luồng tính tiền hoặc FSM.
- Phase 3 (camera reader, YOLO, tracking) ngoài những gì UI đang có.
