# Danh sách file bàn giao Phase 0–2 và GitHub workflow

AGENTS.md ban đầu rỗng được cập nhật. Hồ sơ gốc chứa thông tin liên hệ chỉ giữ local trong docs/references và không đưa lên GitHub công khai. Không bao gồm .venv, node_modules, dist, .env hoặc SQLite runtime.

Tổng cộng 70 file source, tài liệu và ảnh kiểm chứng được đưa vào Git (bao gồm danh sách này và CI).

- `.env.example`
- `.github/workflows/ci.yml`
- `.gitignore`
- `AGENTS.md`
- `README.md`
- `apps/api/billing.py`
- `apps/api/config.py`
- `apps/api/main.py`
- `apps/api/models.py`
- `apps/api/schemas.py`
- `apps/api/tests/test_api.py`
- `apps/web/index.html`
- `apps/web/package-lock.json`
- `apps/web/package.json`
- `apps/web/public/favicon.svg`
- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `apps/web/src/format.test.ts`
- `apps/web/src/format.ts`
- `apps/web/src/main.tsx`
- `apps/web/src/style.css`
- `apps/web/src/types.ts`
- `apps/web/tsconfig.json`
- `apps/web/vite.config.ts`
- `configs/decision.toml`
- `configs/zones.example.json`
- `data/README.md`
- `docs/ai/DATASET_PLAN.md`
- `docs/ai/DETECTION_PIPELINE.md`
- `docs/ai/EVALUATION_METRICS.md`
- `docs/ai/MODEL_STRATEGY.md`
- `docs/ai/ZONE_CALIBRATION.md`
- `docs/architecture/ADR/0001-local-monolith.md`
- `docs/architecture/API_SPEC.md`
- `docs/architecture/DATABASE_DESIGN.md`
- `docs/architecture/DATA_FLOW.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/competition/DEMO_SCRIPT.md`
- `docs/competition/MVP_EVIDENCE.md`
- `docs/competition/PITCH_TECHNICAL_POINTS.md`
- `docs/hardware/BILL_OF_MATERIALS.md`
- `docs/hardware/CAMERA_SETUP.md`
- `docs/hardware/HARDWARE_REQUIREMENTS.md`
- `docs/planning/FILE_MANIFEST.md`
- `docs/planning/GITHUB_ISSUES.md`
- `docs/planning/MILESTONES.md`
- `docs/planning/PHASE_0_2_REPORT.md`
- `docs/planning/REPOSITORY_ASSESSMENT.md`
- `docs/planning/RISKS.md`
- `docs/planning/ROADMAP.md`
- `docs/planning/TASK_BACKLOG.md`
- `docs/planning/TEAM_ASSIGNMENT.md`
- `docs/product/MVP_SCOPE.md`
- `docs/product/PRD.md`
- `docs/product/USER_STORIES.md`
- `docs/references/README.md`
- `docs/testing/DEMO_ACCEPTANCE.md`
- `docs/testing/TEST_CASES.md`
- `docs/testing/TEST_PLAN.md`
- `docs/testing/TEST_RESULTS.md`
- `docs/testing/dashboard-preview.jpg`
- `pyproject.toml`
- `requirements.lock.txt`
- `requirements.txt`
- `scripts/simulate.py`
- `scripts/smoke.py`
- `services/vision/README.md`
- `services/vision/contracts.py`
- `services/vision/decision.py`
- `services/vision/tests/test_decision.py`

## Bổ sung sau Phase 2 (nhánh tích hợp camera/AI)

Danh sách trên là bản bàn giao Phase 0–2. Các file mới thêm sau đó gồm: `apps/api/runtime_settings.py`, `apps/web/src/views/` (TablesView, LabView, LiveView, HistoryView, SystemView, SettingsEditor), `apps/web/src/VideoAutomationPanel.tsx`, `apps/web/src/RoiEditor.tsx`, `apps/web/src/views.test.tsx`, `services/vision/*` (detector, tracker, mapper, pose_analyzer, runner, pipeline, annotator…) cùng test tương ứng, `scripts/evaluate_video.py`, `extract_frames.py`, `train_cue.py`, `record_camera.py`, và các tài liệu `docs/planning/{UI_REORGANIZATION_PLAN,MULTI_TABLE_ROI_PLAN,MODEL_AND_PRODUCT_MVP_PLAN}.md`. File runtime không commit: `data/runtime_settings.json`, `models/*.onnx`, `configs/zones.backup-*.json` (bản sao lưu ROI tạm).
