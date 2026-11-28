"""scripts/qa_video.py のストリーム仕様検証ロジックの単体テスト。"""
from __future__ import annotations

from qa_video import is_valid_stream_spec


def test_stream_spec_accepts_standard_resolutions_and_fps():
    assert is_valid_stream_spec(1080, 1920, 30.0, 16.0) is True
    assert is_valid_stream_spec(1920, 1080, 30.0, 16.0) is True
    assert is_valid_stream_spec(540, 960, 24.0, 16.0) is True
    assert is_valid_stream_spec(1280, 720, 30.0, 15.9) is True


def test_stream_spec_rejects_invalid_resolution_fps_or_duration():
    assert is_valid_stream_spec(640, 480, 30.0, 16.0) is False
    assert is_valid_stream_spec(1080, 1920, 60.0, 16.0) is False
    assert is_valid_stream_spec(1080, 1920, 30.0, 20.0) is False
    assert is_valid_stream_spec(0, 0, 30.0, 16.0) is False
