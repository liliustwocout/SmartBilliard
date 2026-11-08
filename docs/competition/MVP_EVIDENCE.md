# Bằng chứng và giới hạn MVP

Ngày bàn giao phần mềm: 08/11/2026 theo múi giờ người dùng.

## Artifacts thực

- Assessment giữ hồ sơ gốc, monorepo và tài liệu tiếng Việt: `docs/planning/REPOSITORY_ASSESSMENT.md`.
- FastAPI/SQLAlchemy SQLite session/billing/FSM/event persistence: `apps/api/`.
- Pure temporal FSM/config tests và CueDetector/VideoSource contracts: `services/vision/`.
- React/Vite/TypeScript/Tailwind dashboard, table detail, simulation, history, WebSocket: `apps/web/`.
- Pytest + Vitest + production build + HTTP/WS smoke: kết quả chạy thực được ghi trong `docs/testing/TEST_RESULTS.md`.

## Không được coi là evidence AI

Observation nhân tạo, clock injected trong test, biểu tượng bàn vẽ bằng CSS và ROI JSON mẫu không phải khung hình camera. Không có inference, tracking video, dataset, cue weights hoặc độ chính xác đo được. Không có camera/video recording dùng làm bằng chứng.

Auto-open nếu bật chỉ là controlled simulation và session source=SIMULATED. Nhân viên confirm cũng giữ evidence_source=SIMULATED. Chưa có phiên nguồn AI.

## Cần bổ sung sau

Video/ảnh calibration được phép, model/version/hash, hardware/settings, raw ground truth/results cho 15 scenarios, near/far breakdown, 4 bàn live và recording có nhãn nguồn. Chưa sign-off Gate B hoặc xác nhận nghiệm thu thay nhóm.
