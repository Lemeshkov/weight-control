from scripts.tune_camera_motion import classify, evaluate


def rows(scores):
    return [{"timestamp_ns": index * 250_000_000, "score": score, "tracks_valid": 20}
            for index, score in enumerate(scores)]


def test_duration_hysteresis_rejects_short_false_stop():
    timeline = classify(rows([10, 1, 10, 1, 1, 1, 1, 10, 10]), "score", 2, 5, 500, 250, 8)
    assert [item["state"] for item in timeline[:3]] == ["MOVING", "MOVING", "MOVING"]
    assert timeline[5]["state"] == "STOPPED"
    assert timeline[-1]["state"] == "MOVING"


def test_evaluation_is_duration_weighted_and_splits_at_markers():
    timeline = [
        {"timestamp_ns": 0, "state": "MOVING"},
        {"timestamp_ns": 2_000_000_000, "state": "STOPPED"},
        {"timestamp_ns": 6_000_000_000, "state": "MOVING"},
        {"timestamp_ns": 8_000_000_000, "state": "MOVING"},
    ]
    result = evaluate(timeline, {"STOPPED": 1_000_000_000, "RESUMED": 5_000_000_000})
    assert result["false_moving_duration_ms"] == 1000
    assert result["false_stop_duration_ms"] == 1000
    assert result["stop_detection_delay_ms"] == 1000
    assert result["resume_detection_delay_ms"] == 1000


def test_low_track_count_becomes_unknown_without_changing_stable_state():
    source = rows([10, 10, 10])
    source[1]["tracks_valid"] = 2
    timeline = classify(source, "score", 2, 5, 500, 250, 8)
    assert [item["state"] for item in timeline] == ["MOVING", "UNKNOWN", "MOVING"]
