from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np
import pytest

from services.vision.calibration import CalibrationConfig
from services.vision.detector import _forward_with_cpu_fallback, _load_onnx_net, YoloCueDetector, prepare_yolo_input, letterbox
from services.vision.onnx_backend import DirectMlNet
from services.vision.performance import VisionPerformanceConfig
from services.vision.runner import CameraRunner
from services.vision.mapper import TableObservationSummary


def test_shared_jpeg_cache_keeps_raw_resolution_and_invalidates_on_new_frame():
    runner = CameraRunner(performance=VisionPerformanceConfig(preview_width=1280))
    runner._latest_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    runner._frame_sequence = 1
    encode = cv2.imencode
    with patch("cv2.imencode", wraps=encode) as spy:
        sequence, first = runner.get_stream_frame(True)
        assert sequence == 1 and runner.get_stream_frame(True)[1] is first
        assert spy.call_count == 1
        image = cv2.imdecode(np.frombuffer(first, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert image.shape == (720, 1280, 3)
        raw = runner.get_latest_frame_jpeg()
        assert cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR).shape == (1080, 1920, 3)
        runner._frame_sequence = 2
        runner.get_stream_frame(True)
        assert spy.call_count == 3
        runner._calibration_cfg = CalibrationConfig(tables=[])
        runner.get_stream_frame(True)
        assert spy.call_count == 4


def test_fast_preset_can_disable_cue_without_loading_or_claiming_a_model(tmp_path):
    path = tmp_path / "cue.onnx"
    path.touch()
    with patch("services.vision.detector._load_onnx_net") as load:
        cue = YoloCueDetector(path, enabled=False)
        load.assert_not_called()
    assert not cue.is_ready and not cue.validated and cue.backend_label == "DISABLED"
    assert cue.detect(np.zeros((480, 640, 3), dtype=np.uint8)) == []


def test_reused_input_buffer_matches_opencv_preprocessing_and_updates_every_frame():
    frame = np.random.default_rng(42).integers(0, 256, (360, 800, 3), dtype=np.uint8)
    padded, ratio, padding = letterbox(frame)
    expected = cv2.dnn.blobFromImage(padded, scalefactor=1 / 255, size=(640, 640), swapRB=True)
    blob, actual_ratio, actual_padding = prepare_yolo_input(frame, (640, 640))
    np.testing.assert_allclose(blob, expected, atol=1e-7)
    assert actual_ratio == ratio and actual_padding == padding
    old = blob.copy()
    updated, _, _ = prepare_yolo_input(np.zeros_like(frame), (640, 640), blob)
    assert updated is blob and not np.array_equal(old, updated)


def _run_fake_frames(valid, *, paused=False):
    runner = CameraRunner(source="test.mp4")
    calls = iter(valid)

    def read(**_):
        success, last = next(calls)
        if last:
            runner._stop_event.set()
        return success, np.zeros((32, 64, 3), dtype=np.uint8) if success else None, [], {}

    runner._pipeline = SimpleNamespace(source=SimpleNamespace(fps=10), detector=SimpleNamespace(is_ready=True),
                                       inference_skipped=paused, process_frame_for_tables=read)
    waits = []
    with patch("services.vision.runner.time.sleep", side_effect=lambda timeout: waits.append(timeout)):
        runner._run_loop()
    return runner, waits


def test_failed_reads_do_not_increment_frame_counter_or_claim_inference_fps():
    runner, _ = _run_fake_frames([(False, False), (False, False), (True, True)])
    assert runner._frame_sequence == 1
    assert runner.measured_fps == 0 and runner.inference_fps == 0


def test_paused_inference_keeps_video_frames_but_reports_zero_ai_fps():
    runner, waits = _run_fake_frames([(True, False), (True, True)], paused=True)
    assert runner._frame_sequence == 2 and runner.inference_fps == 0
    assert runner.measured_fps > 0
    assert waits[0] > .05  # 10 FPS source is paced below the 30 FPS target.


def test_directml_runtime_failure_reports_real_cpu_fallback():
    net = object.__new__(DirectMlNet)
    net.backend_label = "DIRECTML:0"
    net.set_input = Mock()
    expected = np.zeros((1, 5, 8400), dtype=np.float32)
    net.forward = Mock(side_effect=[RuntimeError("device lost"), expected])
    net.use_cpu = lambda: setattr(net, "backend_label", "ORT_CPU")
    output, backend = _forward_with_cpu_fallback(net, np.zeros((1, 3, 640, 640)), "DIRECTML:0")
    assert output is expected and backend == "ORT_CPU"
    assert net.forward.call_count == 2


def test_observations_are_throttled_without_skipping_inference_frames(monkeypatch):
    runner = CameraRunner(source="clip.mp4")
    tick = [0.0]
    processed = [0]
    emitted = []
    monkeypatch.setattr("services.vision.runner.time.perf_counter", lambda: tick[0])

    def read(**_):
        tick[0] += 1 / 30
        processed[0] += 1
        if processed[0] == 10:
            runner._stop_event.set()
        return True, np.zeros((32, 64, 3), dtype=np.uint8), [], {1: TableObservationSummary(1, True, .9)}

    runner._pipeline = SimpleNamespace(source=SimpleNamespace(fps=30), detector=SimpleNamespace(is_ready=True),
                                       inference_skipped=False, process_frame_for_tables=read)
    runner.on_observation = lambda *args: emitted.append(args)
    monkeypatch.setattr("services.vision.runner.time.sleep", lambda _: None)
    runner._run_loop()
    assert runner._frame_sequence == 10
    assert len(emitted) == 2


def test_unavailable_gpu_initialization_preserves_opencv_fallback(tmp_path):
    path = tmp_path / "test.onnx"
    path.touch()
    with patch("services.vision.detector.DirectMlNet", side_effect=ImportError), \
         patch("cv2.dnn.readNetFromONNX", return_value=object()) as load, \
         patch("services.vision.detector._configure_dnn_backend", return_value="CPU"):
        net, backend = _load_onnx_net(path)
        assert net is load.return_value and backend == "CPU"


@pytest.mark.parametrize("values", [{"target_fps": 0}, {"target_fps": 2}, {"dml_device_id": -1},
                                     {"preview_width": 0}, {"opencv_threads": 0}])
def test_invalid_performance_config_is_rejected(values):
    with pytest.raises(ValueError):
        VisionPerformanceConfig(**values)


def _fake_ort_session(providers):
    session = Mock()
    session.get_providers.return_value = list(providers)
    session.get_inputs.return_value = [SimpleNamespace(name="images")]
    return session


def test_directml_init_falls_back_to_ort_cpu_on_machines_without_dx12_gpu(tmp_path):
    model = tmp_path / "pose.onnx"
    model.write_bytes(b"onnx")

    # Case 1: Only CPUExecutionProvider is compiled in (e.g. non-DirectML environment)
    fake_ort_no_dml = SimpleNamespace(
        SessionOptions=lambda: SimpleNamespace(),
        ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL=0),
        get_available_providers=lambda: ["CPUExecutionProvider"],
        InferenceSession=Mock(return_value=_fake_ort_session(["CPUExecutionProvider"])),
    )
    with patch.dict("sys.modules", {"onnxruntime": fake_ort_no_dml}):
        net = DirectMlNet(model, device_id=0)
        assert net.backend_label == "ORT_CPU"

    # Case 2: DmlExecutionProvider listed but fails on CPU-only PC / VM -> falls back to ORT_CPU
    cpu_session = _fake_ort_session(["CPUExecutionProvider"])
    def create_session(_path, sess_options=None, providers=None):
        if providers and any(isinstance(p, tuple) and p[0] == "DmlExecutionProvider" for p in providers):
            raise RuntimeError("No DX12 adapter")
        return cpu_session

    fake_ort_fail_dml = SimpleNamespace(
        SessionOptions=lambda: SimpleNamespace(),
        ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL=0),
        get_available_providers=lambda: ["DmlExecutionProvider", "CPUExecutionProvider"],
        InferenceSession=Mock(side_effect=create_session),
    )
    with patch.dict("sys.modules", {"onnxruntime": fake_ort_fail_dml}):
        net = DirectMlNet(model, device_id=0)
        assert net.backend_label == "ORT_CPU"


def test_directml_init_retries_default_adapter_zero_when_configured_adapter_missing(tmp_path):
    model = tmp_path / "pose.onnx"
    model.write_bytes(b"onnx")
    seen_devices = []

    def create_session(_path, sess_options=None, providers=None):
        dev = int(providers[0][1]["device_id"])
        seen_devices.append(dev)
        if dev != 0:
            raise RuntimeError("Invalid adapter index")
        return _fake_ort_session(["DmlExecutionProvider", "CPUExecutionProvider"])

    fake_ort = SimpleNamespace(
        SessionOptions=lambda: SimpleNamespace(),
        ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL=0),
        get_available_providers=lambda: ["DmlExecutionProvider", "CPUExecutionProvider"],
        InferenceSession=Mock(side_effect=create_session),
    )
    with patch.dict("sys.modules", {"onnxruntime": fake_ort}):
        net = DirectMlNet(model, device_id=1)
        assert seen_devices == [1, 0]
        assert net.device_id == 0
        assert net.backend_label == "DIRECTML:0"
