# GitHub issues và milestones

Repository: [liliustwocout/SmartBilliard](https://github.com/liliustwocout/SmartBilliard).

Owner là phân công đề xuất theo kế hoạch, chưa phải GitHub assignee. Chưa có ngày kickoff/deadline được xác nhận nên milestone không đặt due date.

## Phase 0–2 đã triển khai

- [[M2] Hoàn thành Phase 0–2: foundation và simulated vertical slice](https://github.com/liliustwocout/SmartBilliard/issues/1): bao phủ SB-01–SB-08; issue đóng khi PR được merge. CI và merge là gate cuối.

## Công việc tiếp theo

### [M3 — Camera foundation](https://github.com/liliustwocout/SmartBilliard/milestone/2)

- [SB-09 · Camera/video adapters](https://github.com/liliustwocout/SmartBilliard/issues/2) — P0; owner: Sơn; phụ thuộc: [SB-08 / M2](https://github.com/liliustwocout/SmartBilliard/issues/1).
- [SB-10 · ROI editor và calibration](https://github.com/liliustwocout/SmartBilliard/issues/3) — P0; owner: Sơn + An; phụ thuộc: [SB-09](https://github.com/liliustwocout/SmartBilliard/issues/2).
- [SB-15 · Dataset và consent](https://github.com/liliustwocout/SmartBilliard/issues/8) — P0; owner: Đức + Sơn; phụ thuộc: [SB-02 / M2](https://github.com/liliustwocout/SmartBilliard/issues/1).

### [M4 — Vision & integration](https://github.com/liliustwocout/SmartBilliard/milestone/3)

- [SB-11 · Person và tracker](https://github.com/liliustwocout/SmartBilliard/issues/4) — P0; owner: Sơn; phụ thuộc: [SB-09](https://github.com/liliustwocout/SmartBilliard/issues/2).
- [SB-12 · Zone assignment](https://github.com/liliustwocout/SmartBilliard/issues/5) — P0; owner: Sơn + Đạt; phụ thuộc: [SB-10](https://github.com/liliustwocout/SmartBilliard/issues/3), [SB-11](https://github.com/liliustwocout/SmartBilliard/issues/4).
- [SB-13 · Camera event integration](https://github.com/liliustwocout/SmartBilliard/issues/6) — P0; owner: Đạt; phụ thuộc: [SB-12](https://github.com/liliustwocout/SmartBilliard/issues/5), [SB-06 / M2](https://github.com/liliustwocout/SmartBilliard/issues/1).
- [SB-14 · MINI_TABLE adapter](https://github.com/liliustwocout/SmartBilliard/issues/7) — P1; owner: Sơn; phụ thuộc: [SB-09](https://github.com/liliustwocout/SmartBilliard/issues/2).
- [SB-16 · Cue model](https://github.com/liliustwocout/SmartBilliard/issues/9) — P2; owner: Sơn; phụ thuộc: [SB-11](https://github.com/liliustwocout/SmartBilliard/issues/4), [SB-15](https://github.com/liliustwocout/SmartBilliard/issues/8).
- [SB-20 · Retention và database evolution](https://github.com/liliustwocout/SmartBilliard/issues/13) — P1; owner: An; phụ thuộc: [SB-08 / M2](https://github.com/liliustwocout/SmartBilliard/issues/1).

### [M5 — Validation & demo](https://github.com/liliustwocout/SmartBilliard/milestone/4)

- [SB-17 · Four-table validation](https://github.com/liliustwocout/SmartBilliard/issues/10) — P0; owner: Đạt + Sơn; phụ thuộc: [SB-13](https://github.com/liliustwocout/SmartBilliard/issues/6), [SB-15](https://github.com/liliustwocout/SmartBilliard/issues/8).
- [SB-18 · Mở rộng tám bàn / 4K](https://github.com/liliustwocout/SmartBilliard/issues/11) — P2; owner: Sơn; phụ thuộc: [SB-17](https://github.com/liliustwocout/SmartBilliard/issues/10).
- [SB-19 · Demo và pitch](https://github.com/liliustwocout/SmartBilliard/issues/12) — P0; owner: Đức; phụ thuộc: [SB-17](https://github.com/liliustwocout/SmartBilliard/issues/10).

## Thứ tự bắt đầu

Sau M2: SB-09 camera/video adapter là luồng kỹ thuật kế tiếp; SB-15 dữ liệu/consent có thể chuẩn bị song song. Tiếp theo SB-10 và SB-11, rồi SB-12 → SB-13 → SB-17 → SB-19. MINI_TABLE là nhánh riêng; cue và tám bàn/4K là thử nghiệm P2. SB-20 xử lý retention/migration trước khi dữ liệu vận hành tăng hoặc thay schema.

Tạo các issue này chỉ để lập kế hoạch; chưa bắt đầu triển khai Phase 3.
