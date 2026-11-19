# Nghiên cứu AI box và cách triển khai SmartBilliard

Ngày rà soát: 18/11/2026. Phạm vi: đánh giá phần cứng cho MVP một quán. Kiến trúc sản phẩm `.exe`/tài khoản/gói được trình bày riêng tại [đề xuất triển khai desktop](../architecture/DESKTOP_PRODUCT_DEPLOYMENT.md). Đây là đánh giá khả năng tương thích và kế hoạch thử nghiệm, **không phải xác nhận hiệu năng hay quyết định mua hàng**. Code vision đang được phát triển song song; kiểm tra lại trạng thái trước khi chốt mua.

## 1. Trạng thái thực tế của repository

| Thành phần | Đã có trong code | Chưa được chứng minh |
| --- | --- | --- |
| Camera | Adapter file, USB, RTSP; `CameraRunner` một nguồn, mục tiêu xử lý 8 FPS | Chạy ổn định trên camera/góc lắp thật; khả năng nhiều camera |
| AI | YOLOv8n ONNX person/pose; code có đường OpenCV DNN CUDA FP16 khi bản OpenCV và thiết bị hỗ trợ, nếu không dùng CPU; ByteTrack, foot anchor và gán ROI | Chưa chứng minh đường GPU thực chạy; độ chính xác gần/xa, che khuất, FPS/độ trễ trên thiết bị đích |
| Model | Code tìm `models/yolov8n-pose.onnx`, fallback `models/yolov8n.onnx`, và model cue riêng | Các file weights chưa có trong repository; test bằng model thật sẽ skip. Khi thiếu model, không có suy luận AI |
| Nghiệp vụ | FastAPI, SQLite, một process, WebSocket, React dashboard, tính tiền ở backend | Quy trình thu tiền thật, phân quyền, audit, bảo mật cho truy cập LAN |
| POS/app | Dashboard web có mở/checkout/lịch sử | Không có POS đầy đủ, tích hợp máy in/hệ thống thanh toán, hay ứng dụng native |

Nguồn nội bộ: `services/vision/detector.py`, `services/vision/runner.py`, `services/vision/tests/test_detector.py`, `apps/api/main.py`, `apps/api/config.py`, `apps/web/package.json`. `README.md` và một số tài liệu kiến trúc còn mô tả trạng thái Phase 2 trước khi các file camera mới được kéo về; dùng code hiện tại làm căn cứ kỹ thuật, đồng thời giữ giới hạn kiểm chứng ở trên. Camera hiện mặc định tắt; API chỉ cho Host/Origin localhost và chưa có xác thực người dùng. Endpoint ingestion và điều khiển camera hiện không phù hợp để mở trực tiếp ra LAN/Internet.

## 2. Tương thích model với AI box

**ONNX là định dạng trao đổi, không đồng nghĩa chạy được trên bộ tăng tốc.** Code gọi `cv2.dnn.readNetFromONNX` và thử CUDA FP16 khi OpenCV phát hiện CUDA, rồi fallback CPU. Vì vậy mua box có GPU/NPU sẽ không tự bảo đảm tăng FPS; cần xác nhận bản OpenCV có CUDA DNN, model load/forward đúng, kiểm tra shape/preprocessing/postprocessing và so kết quả với CPU trên cùng clip. Có thể thêm adapter TensorRT/OpenVINO/Hailo nếu đường OpenCV không đạt. [OpenCV backend/target](https://docs.opencv.org/4.12.0/db/d30/classcv_1_1dnn_1_1Net.html), [OpenCV build options](https://docs.opencv.org/4.12.0/db/d05/tutorial_config_reference.html).

| Phương án | Mức phù hợp với code hiện tại | Khi nào chọn |
| --- | --- | --- |
| **Mini PC x86 có CPU đủ mạnh** | Cao nhất: giữ Python/OpenCV DNN CPU, FastAPI, SQLite và web trên cùng máy. Đây là **đề xuất thử đầu tiên**; CPU cụ thể chưa được chứng nhận đạt 8 FPS. | Một camera/3–4 bàn để xác minh góc nhìn và nghiệp vụ; ưu tiên giảm công tích hợp. Có thể thử OpenVINO CPU/GPU sau bằng adapter riêng; OpenVINO hỗ trợ ONNX và các device CPU/GPU/NPU nhưng phụ thuộc driver, model và thiết bị. [OpenVINO model preparation](https://docs.openvino.ai/2025/openvino-workflow/model-preparation.html), [supported devices](https://docs.openvino.ai/2026/documentation/compatibility-and-support/supported-devices.html). |
| **Jetson Orin Nano Super Developer Kit, 8 GB** | Thử đường OpenCV CUDA FP16 hiện có trên bản OpenCV được build phù hợp; nếu không đạt, đưa ONNX sang TensorRT và thêm adapter. Cài JetPack phù hợp, chạy/test trên thiết bị. NVIDIA công bố tối đa 67 INT8 TOPS và 7–25 W; đó không phải FPS SmartBilliard. [NVIDIA specs](https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/nano-super-developer-kit/), [TensorRT ONNX](https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/architecture/capabilities.html). | Khi cần box gọn/tiết kiệm điện và nhóm sẵn sàng xác minh toolchain GPU. Dùng kit để nguyên mẫu, không mặc nhiên dùng làm sản phẩm triển khai lâu dài: NVIDIA nêu developer kit chứa module không theo đặc tả production. [Jetson quick start](https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/IN/QuickStart.html). |
| **Jetson Orin NX 16 GB + carrier** | Cùng hướng TensorRT, chi phí và độ phức tạp cao hơn. NVIDIA công bố tối đa 157 sparse INT8 TOPS; chưa suy ra số camera/bàn chạy được. [NVIDIA module specs](https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/). | Chỉ đánh giá sau khi Nano/x86 không đáp ứng benchmark nhiều luồng hoặc model nặng hơn; tính cả carrier, nguồn, NVMe, tản nhiệt, vỏ và bảo hành vào báo giá. |
| **Hailo-8 M.2 / NPU chuyên dụng** | Không chạy trực tiếp bằng backend OpenCV hiện tại. Cần host phù hợp, chuyển/biên dịch model sang định dạng thiết bị và runtime riêng; phải kiểm tra operator và sai lệch sau lượng tử hóa. [Hailo product brief](https://hailo.ai/hailo-files/hailo-8-m-2-et-product-brief-en/). | Chỉ chọn khi có người phụ trách toolchain/benchmark và lợi ích điện năng hoặc số luồng đã đo vượt công tích hợp. |

JetPack có ràng buộc phiên bản CUDA/TensorRT; không lấy hướng dẫn TensorRT desktop mới nhất áp thẳng lên Orin. [JetPack 6.2 release notes](https://docs.nvidia.com/jetson/jetpack/6.2/release-notes/index.html). YOLOv8 COCO pretrained không nhận gậy bi-a; code đã có interface/model cue riêng nhưng chưa có weights hoặc đánh giá. Cảnh bàn mini chỉ thấy tay cần bài toán khác. Tốc độ cao hơn không sửa được góc camera sai hay người quá nhỏ ở vùng xa. Nếu thương mại hóa, rà soát license weights/model YOLOv8 trước khi phân phối: Ultralytics nêu lựa chọn AGPL-3.0 và Enterprise. [Ultralytics YOLOv8](https://docs.ultralytics.com/models/yolov8).

### Cấu hình hỏi báo giá, chưa phải mức tối thiểu đã chứng nhận

- **Cho pilot x86:** mini PC x86_64, RAM 16 GB (ưu tiên nâng 32 GB), NVMe 512 GB, Ethernet 1 GbE, ít nhất một cổng USB 3, tản nhiệt chủ động, nguồn ổn định và UPS. Yêu cầu bên bán cho mượn/đổi trả để benchmark với clip/camera thật trước khi chốt CPU cụ thể.
- **Nếu chọn Jetson để thử:** Orin Nano Super Developer Kit 8 GB, NVMe, nguồn/tản nhiệt đúng kit, Ethernet; kiểm tra image JetPack, Python/dependency tương thích, TensorRT engine và FPS trên chính kit. Kit có Ethernet, USB và khe NVMe theo [hướng dẫn phần cứng NVIDIA](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/hardware_layout.html). Camera PoE cần switch/injector riêng; cổng Ethernet của kit không cấp PoE cho camera.
- **Camera và mạng:** ưu tiên camera IP RTSP cố định, có dây Ethernet, nguồn/PoE phù hợp, ánh sáng ổn định; lắp thử và vẽ ROI trên khung hình thật. Một camera bao được 3–4 bàn là giả thuyết cần xác minh; 8 bàn/4K là bài đo riêng. Không chốt model box chỉ dựa vào con số TOPS hoặc nhãn “AI box”.

## 3. Cách triển khai hệ thống

### Khuyến nghị cho pilot một quán

```text
Camera USB/RTSP ──> máy edge tại quán
                     ├─ Vision: person → tracking → ROI → Observation
                     ├─ FastAPI: FSM, phiên bàn, giá/tiền chính thức
                     ├─ SQLite + sao lưu có kiểm soát
                     └─ React build + WebSocket
                              │
                         Trình duyệt nhân viên
                         (PC/POS terminal/tablet)
```

1. **Giai đoạn kiểm chứng:** chạy một máy edge + một camera + dashboard web trên chính máy đó/loopback. Nhân viên xác nhận mở bàn và checkout; `AUTO_OPEN_ENABLED=false`. Dùng clip có nhãn và camera thật để đo sai/mất nhận diện, FPS, latency và tài nguyên. Không ghi “AI đang chạy” nếu thiếu weights hoặc detector chưa sẵn sàng.
2. **Giai đoạn vận hành LAN:** sau khi qua kiểm chứng, cho terminal nhân viên mở web responsive qua mạng nội bộ. Trước khi đổi binding localhost phải bổ sung đăng nhập/phân quyền, xác thực cả REST/WS/ingestion, kiểm soát Origin/Host theo tên miền LAN, TLS hoặc mạng cách ly, audit thao tác, bảo vệ RTSP credentials, startup service, giám sát nguồn camera, backup/migration SQLite. Giữ một backend process trong phạm vi kiến trúc hiện tại; không nhân nhiều Uvicorn workers với state/SQLite hiện hữu.
3. **Giai đoạn nhiều camera hoặc nhiều quán:** tách camera worker khỏi backend bằng hàng đợi/buffer giới hạn và ingestion service có xác thực, timestamp/frame age/idempotency; chỉ đổi database khi thật sự cần nhiều writer/thiết bị/quán. Mỗi camera phải có ROI và đánh giá riêng. Đây là thiết kế tương lai, chưa phải chức năng đã hoàn tất.

### POS, web hay app?

| Lựa chọn | Khuyến nghị |
| --- | --- |
| **Web trên PC/tablet/POS terminal** | Ưu tiên. Repository đã có React dashboard và API; một bản cập nhật phục vụ mọi màn hình trong LAN. Nếu dùng tablet, kiểm tra bố cục cảm ứng và mất kết nối. PWA có thể cân nhắc sau, nhưng không thay thế backend offline tại quán. |
| **POS đầy đủ** | Chưa nên xây riêng cho MVP vì PRD không bao gồm F&B, tồn kho, máy in, thuế, thanh toán. Nếu quán đã có POS: SmartBilliard là nguồn chính thức của thời gian/giá/tiền bàn; gửi `table_id`, `session_id`, số tiền đã chốt sang POS bằng API có khóa idempotency; POS quản lý trạng thái thanh toán và các món khác. Chỉ đánh dấu đã thanh toán khi có xác nhận từ POS/nhân viên, có đối soát và xử lý retry. |
| **App native** | Chưa cần cho nhân viên; thêm hai bản build, phân phối và bảo trì khi web đã đủ luồng. Xem xét riêng nếu cần camera/thiết bị cục bộ trên điện thoại, notification nền đáng tin cậy hoặc offline trên từng thiết bị. |

Dashboard hiện có thao tác “checkout” và ghi số tiền demo, **chưa tích hợp cổng thanh toán hay xác nhận tiền chuyển thực**. Không đưa API hiện tại ra Internet. Nếu sau này khách hàng xem trạng thái bàn từ bên ngoài, cần API đọc riêng và chính sách dữ liệu riêng, không expose luồng camera/điều khiển nội bộ.

## 4. Quy trình quyết định mua

1. Chuẩn bị ít nhất một clip/camera thật có sự đồng ý, gồm tình huống gần, xa, che khuất, đi ngang, bàn trống và nhiều người; gán nhãn theo bàn. Lưu clip ngoài Git và theo chính sách dữ liệu.
2. Lấy đúng weights ONNX, version/hash và license; xác nhận model load được, output đúng shape, detection thật thay vì fallback rỗng. Trước pilot, sửa trạng thái sẵn sàng để thiếu/lỗi weights báo lỗi rõ và không cho bật chế độ AI. Soát ảnh hưởng của input `640 × 640` ở bàn xa.
3. Trên máy đang có, đo một ca chạy đại diện: FPS **xử lý inference** (khác FPS vòng lặp), p95 từ capture đến dashboard, frame age, CPU/RAM, số event và false/missed opening. `target_fps=8` trong code là nhịp mục tiêu, **không phải số đo**. Chốt ngưỡng chấp nhận trước khi thử box; có thể lấy 8 FPS xử lý và p95 dưới 1 giây làm mục tiêu pilot để thảo luận, không công bố là kết quả.
4. Nếu CPU đạt và chất lượng hình đủ: thử mini PC x86 trước. Nếu CPU không đạt: benchmark cùng clip trên Jetson/TensorRT hoặc x86/OpenVINO. Chỉ báo giá/mua sau khi có bảng kết quả trên chính thiết bị ứng viên, đủ cả phụ kiện và điều kiện bảo hành tại Việt Nam.
5. Trước pilot LAN, hoàn thành các điều kiện bảo mật và backup ở mục 3. Trước tự mở phiên tính tiền, cần kiểm chứng nghiệp vụ/false auto-open bằng video thật; giữ xác nhận nhân viên mặc định.

**Kết luận:** mua một mini PC x86 để *thử* là lộ trình ít sửa code nhất nếu laptop sẵn có không đủ; Jetson Orin Nano Super là ứng viên AI box hợp lý để *benchmark* khi cần tăng tốc GPU. Chưa có dữ liệu để bảo đảm một SKU nào xử lý 3–4 bàn, càng chưa thể chốt 8 bàn. Hệ thống nên bắt đầu bằng web nội bộ trên một máy edge; tích hợp POS sau khi có quán/pipeline thanh toán cụ thể; chưa cần app native.
