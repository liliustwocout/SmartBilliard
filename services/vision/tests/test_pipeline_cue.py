"""Experimental cue inference stays visible but is excluded from table decisions."""
from unittest.mock import MagicMock

import numpy as np
import pytest

from services.vision.contracts import Detection
from services.vision.detector import PersonDetection
from services.vision.pipeline import VisionPipeline


@pytest.mark.parametrize("validated", [False, True])
def test_loaded_cue_is_previewed_but_only_validated_cue_reaches_mapper(validated):
    source = MagicMock(camera_id="test")
    source.read.return_value = (True, np.zeros((320, 640, 3), dtype=np.uint8))
    person = PersonDetection((.2, .2, .4, .8), .9, (.3, .8), track_id=1)
    detector = MagicMock()
    detector.detect.return_value = [person]
    tracker = MagicMock()
    tracker.update.return_value = [person]
    cue = Detection("test", 12.5, "cue", (.25, .4, .8, .45), .8)
    cue_detector = MagicMock(is_ready=True, validated=validated)
    cue_detector.detect.return_value = [cue]
    mapper = MagicMock()
    mapper.map_frame.return_value = ([], {})
    pipe = VisionPipeline(source, detector=detector, tracker=tracker, mapper=mapper,
                          cue_detector=cue_detector)
    ok, _, detections, _ = pipe.process_frame_for_tables(timestamp=12.5)
    assert ok and [d.kind for d in detections] == ["person", "cue"]
    cue_detector.detect.assert_called_once()
    mapped = mapper.map_frame.call_args.args[0]
    assert [d.kind for d in mapped] == (["person", "cue"] if validated else ["person"])


def test_unloaded_cue_detector_is_not_called():
    source = MagicMock(camera_id="test")
    source.read.return_value = (True, np.zeros((32, 64, 3), dtype=np.uint8))
    detector, tracker = MagicMock(), MagicMock()
    tracker.update.return_value = [PersonDetection((.2, .2, .4, .8), .9, (.3, .8), track_id=1)]
    cue_detector = MagicMock(is_ready=False, validated=False)
    VisionPipeline(source, detector=detector, tracker=tracker,
                   cue_detector=cue_detector).process_next_frame()
    cue_detector.detect.assert_not_called()
