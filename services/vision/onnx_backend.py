"""Optional DirectML execution of the same ONNX graphs used by OpenCV."""
from pathlib import Path

import numpy as np


class DirectMlNet:
    """Single-thread-owned inference adapter; each detector has its own session."""

    def __init__(self, model_path: Path, device_id: int = 0) -> None:
        import onnxruntime as ort

        self._ort = ort
        self.model_path = model_path
        self.device_id = device_id
        self._blob: np.ndarray | None = None
        if "DmlExecutionProvider" in ort.get_available_providers():
            try:
                self._create_session(gpu=True)
                return
            except Exception:
                if self.device_id != 0:
                    try:
                        self.device_id = 0
                        self._create_session(gpu=True)
                        return
                    except Exception:
                        pass
        self._create_session(gpu=False)

    def _create_session(self, *, gpu: bool) -> None:
        opts = self._ort.SessionOptions()
        opts.enable_mem_pattern = False
        opts.execution_mode = self._ort.ExecutionMode.ORT_SEQUENTIAL
        opts.intra_op_num_threads = 1 if gpu else 2
        providers = ([("DmlExecutionProvider", {"device_id": str(self.device_id)}), "CPUExecutionProvider"]
                     if gpu else ["CPUExecutionProvider"])
        self._session = self._ort.InferenceSession(str(self.model_path), sess_options=opts, providers=providers)
        if gpu:
            self._session.disable_fallback()
            if "DmlExecutionProvider" not in self._session.get_providers():
                raise RuntimeError("DirectML session fell back during initialization")
        self._input_name = self._session.get_inputs()[0].name
        self.backend_label = f"DIRECTML:{self.device_id}" if gpu else "ORT_CPU"

    def set_input(self, blob: np.ndarray) -> None:
        self._blob = np.ascontiguousarray(blob, dtype=np.float32)

    def forward(self) -> np.ndarray:
        return self._session.run(None, {self._input_name: self._blob})[0]

    def use_cpu(self) -> None:
        self._create_session(gpu=False)
