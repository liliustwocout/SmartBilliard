# Setup camera — checklist Phase 3

1. Dựng 3–4 bàn, chốt vị trí camera và khoảng cách gần/xa; chừa standing zones trong frame.
2. USB: kiểm tra camera index/permission với ứng dụng hệ thống. RTSP: kiểm tra stream trong mạng local, password chỉ lưu `.env`, không chụp/log credential.
3. Chốt resolution/FPS/exposure; tránh autofocus thay đổi trong demo nếu có thể. Lưu ảnh tham chiếu được phép để hiệu chuẩn.
4. Chọn REAL_CLUB khi có người thật; MINI_TABLE khi chỉ thấy tay/gậy mini. Không dùng detection mode sai.
5. Vẽ và kiểm tra ROI theo ZONE_CALIBRATION, thử giữa hai bàn và đi ngang.
6. Test rút USB/ngắt RTSP/reconnect, đọc frame thất bại, giới hạn FPS và stale-frame handling. Trạng thái camera phải có cảnh báo rõ.
7. Tải weights local và test offline trước demo. Lưu configs/versions, không lưu video ngoài mục đích đã đồng ý.

Các env `CAMERA_SOURCE=0` (USB), URI RTSP hoặc đường dẫn video là kế hoạch adapter. **Phase 2 chưa đọc chúng, chưa có lệnh capture/AI**. Không dùng ảnh bàn vẽ trong dashboard làm camera preview.
