# Backlog

Quy ước: P0 bắt buộc demo; P1 quan trọng; P2 thử nghiệm. DONE chỉ cho phạm vi code/tài liệu đã có; không đồng nghĩa kiểm chứng camera.

Theo dõi thực thi tại [GitHub issues và milestones](GITHUB_ISSUES.md). SB-01–SB-08 nằm trong issue M2; SB-09–SB-20 có issue riêng cùng liên kết phụ thuộc.

## SB-01 · Kiểm kê repository
- Description: ghi inventory, tài liệu có thể giữ, môi trường và rủi ro.
- Owner: Đạt. Priority: P0. Dependencies: không.
- Acceptance Criteria: không ghi đè hồ sơ; assessment có giới hạn scope.
- Status: DONE (Phase 0).

## SB-02 · Kiến trúc và kế hoạch
- Description: PRD, ADR, database/API, roadmap, phân công và acceptance.
- Owner: Đạt + Đức. Priority: P0. Dependencies: SB-01.
- Acceptance Criteria: tài liệu tiếng Việt có điểm dừng Phase 2, không claim AI.
- Status: DONE (Phase 1).

## SB-03 · Session và SQLite
- Description: schema, seed bốn bàn, manual open, active uniqueness, history.
- Owner: An. Priority: P0. Dependencies: SB-02.
- Acceptance Criteria: retry/concurrent open cùng bàn chỉ một session; restart giữ dữ liệu.
- Status: DONE (Phase 2 implementation).

## SB-04 · Billing backend
- Description: snapshot giá, UTC, số nguyên VND, phút làm tròn lên và checkout theo session ID.
- Owner: An. Priority: P0. Dependencies: SB-03.
- Acceptance Criteria: biên 60 giây/60 giây+1µs, rate change, checkout replay đều có tests.
- Status: DONE (Phase 2 implementation).

## SB-05 · Temporal FSM
- Description: presence, confidence/hysteresis, max gap, grace, cooldown, cue guard.
- Owner: Đạt. Priority: P0. Dependencies: SB-02.
- Acceptance Criteria: mặc định xác nhận; ambiguity/passers không mở; absence không đóng ACTIVE.
- Status: DONE (unit logic; chưa video validation).

## SB-06 · Simulated ingestion
- Description: UUID idempotency, source nhãn cố định, transactional decision/session/event.
- Owner: Đạt + An. Priority: P0. Dependencies: SB-03, SB-05.
- Acceptance Criteria: replay không cộng hiện diện; khác payload cùng ID trả 409; auto mở ghi SIMULATED.
- Status: DONE (Phase 2 implementation).

## SB-07 · Dashboard và WebSocket
- Description: bàn, chi tiết, history, simulated controls, reconnect/stale UI.
- Owner: An. Priority: P0. Dependencies: SB-04, SB-06.
- Acceptance Criteria: nhận quote server, không tính phí frontend, nhãn mô phỏng luôn nhìn thấy.
- Status: DONE (Phase 2 implementation; checks xem TEST_RESULTS).

## SB-08 · Tests và offline handoff
- Description: Pytest, Vitest, build, HTTP/WS smoke và runbook.
- Owner: An + Đạt. Priority: P0. Dependencies: SB-07.
- Acceptance Criteria: test DB tạm; built web chạy local; báo rõ camera chưa kiểm chứng.
- Status: DONE (39 Pytest, 3 Vitest, build và HTTP/WS smoke đã đạt; browser QA đã thực hiện). Không dùng kết quả unit để thay camera evidence.

## SB-09 · Camera/video adapters
- Description: USB/RTSP/file cùng VideoSource, reconnect/backoff, trạng thái mất frame, env.
- Owner: Sơn. Priority: P0. Dependencies: SB-08.
- Acceptance Criteria: nguồn thực, loss/recovery không mở nhầm, không log password RTSP.
- Status: TODO (milestone tiếp theo).

## SB-10 · ROI editor và calibration
- Description: preview, vẽ/lưu play/standing polygon chuẩn hóa cho từng bàn.
- Owner: Sơn + An. Priority: P0. Dependencies: SB-09.
- Acceptance Criteria: 4 bàn đúng camera/resolution, polygon hợp lệ, overlap báo ambiguity.
- Status: TODO.

## SB-11 · Person và tracker
- Description: YOLO pretrained person, ByteTrack/BoT-SORT, bbox/confidence/time/camera/track ID.
- Owner: Sơn. Priority: P0. Dependencies: SB-09.
- Acceptance Criteria: đọc weights local, không tải khi demo, không lưu danh tính.
- Status: TODO.

## SB-12 · Zone assignment
- Description: foot anchor, standing zones, không tùy tiện gán nhiều bàn.
- Owner: Sơn + Đạt. Priority: P0. Dependencies: SB-10, SB-11.
- Acceptance Criteria: đi ngang/giữa hai bàn/che khuất có labeled video test, unknown → AMBIGUOUS.
- Status: TODO.

## SB-13 · Camera event integration
- Description: đưa observations thật vào FSM qua ingestion có xác thực riêng; queue có giới hạn.
- Owner: Đạt. Priority: P0. Dependencies: SB-12, SB-06.
- Acceptance Criteria: source CAMERA/VIDEO đúng thực tế; stale/buffered frame không mở phiên; không chặn WS.
- Status: TODO.

## SB-14 · MINI_TABLE adapter
- Description: đánh giá hand detector khi không thấy toàn thân; policy yêu cầu xác nhận riêng.
- Owner: Sơn. Priority: P1. Dependencies: SB-09.
- Acceptance Criteria: nhãn MINI_TABLE, báo cáo tách REAL_CLUB, không suy diễn accuracy người từ tay.
- Status: TODO.

## SB-15 · Dataset và consent
- Description: clip thực được đồng ý, nhãn presence/zone/session, split theo cảnh/quán.
- Owner: Đức + Sơn. Priority: P0. Dependencies: SB-02.
- Acceptance Criteria: dataset manifest, consent/retention, split tránh leakage; không commit video cá nhân.
- Status: TODO.

## SB-16 · Cue model
- Description: thu nhãn cue, fine-tune custom weights và đánh giá false positives; COCO không thay thế.
- Owner: Sơn. Priority: P2. Dependencies: SB-11, SB-15.
- Acceptance Criteria: holdout precision/recall và gate được Đạt duyệt; chưa đạt thì giữ CUE_NOT_READY.
- Status: TODO (interface đã có).

## SB-17 · Four-table validation
- Description: 15 tình huống trên camera thật, near/far, throughput/resource/event latency.
- Owner: Đạt + Sơn. Priority: P0. Dependencies: SB-13, SB-15.
- Acceptance Criteria: raw results có hardware/settings/video IDs, confusion counts, mở nhầm/bỏ sót; không bịa metrics.
- Status: TODO.

## SB-18 · Mở rộng tám bàn / 4K
- Description: đo độ phân giải vùng xa, CPU/GPU và vùng gần/xa riêng.
- Owner: Sơn. Priority: P2. Dependencies: SB-17.
- Acceptance Criteria: báo đạt/không đạt theo từng bàn, không hứa một camera đủ tám bàn.
- Status: TODO.

## SB-19 · Demo và pitch
- Description: tập offline, kịch bản camera/video/simulation riêng, quay evidence có nguồn.
- Owner: Đức. Priority: P0. Dependencies: SB-17.
- Acceptance Criteria: runbook, recording có nguồn/timestamp, biết fallback thủ công.
- Status: TODO (script và pitch outline đã có).

## SB-20 · Retention và database evolution
- Description: xác định retention/idempotency window; migration có backup khi schema thay.
- Owner: An. Priority: P1. Dependencies: SB-08.
- Acceptance Criteria: không xóa event key đang trong cửa sổ retry; giữ nguyên history/session.
- Status: TODO (chưa cần background job cho Phase 2).
