import dataclasses
import json

from scripts.summarize_motion_validation import summarize
from scripts.validate_camera_motion import (
    FIXED_CANDIDATE,
    TUNING_SESSION_KEY,
    criteria_result,
    duration_metrics,
    fixed_hysteresis,
    parse_ground_truth,
    simulate_profiles,
    transitions,
    truth_at,
)


def motion_rows(scores, step_ms=250):
    return [{"timestamp_ns": index * step_ms * 1_000_000, "motion_score": score}
            for index, score in enumerate(scores)]


def states(scores, step_ms=250):
    return [row["predicted_state"] for row in fixed_hysteresis(motion_rows(scores, step_ms))]


def test_candidate_parameters_are_frozen_and_exact():
    assert FIXED_CANDIDATE.stop_threshold == 1.361371e-05
    assert FIXED_CANDIDATE.start_threshold == 0.00887307
    assert FIXED_CANDIDATE.stop_confirmation_ms == 2000
    assert FIXED_CANDIDATE.resume_confirmation_ms == 750
    try:
        FIXED_CANDIDATE.stop_threshold = 1
        assert False
    except dataclasses.FrozenInstanceError:
        pass


def test_fixed_hysteresis_does_not_derive_parameters_from_dataset():
    first = fixed_hysteresis(motion_rows([100.0, 0.0]))
    second = fixed_hysteresis(motion_rows([1e-20, 1e20]))
    for timeline in (first, second):
        assert all(row["stop_threshold"] == FIXED_CANDIDATE.stop_threshold for row in timeline)
        assert all(row["start_threshold"] == FIXED_CANDIDATE.start_threshold for row in timeline)


def test_stop_requires_full_confirmation_duration():
    low = FIXED_CANDIDATE.stop_threshold / 2
    timeline = fixed_hysteresis(motion_rows([1.0] + [low] * 10, 250))
    assert timeline[8]["predicted_state"] == "MOVING"
    assert timeline[9]["predicted_state"] == "STOPPED"


def test_resume_requires_full_confirmation_duration():
    low, high = FIXED_CANDIDATE.stop_threshold / 2, FIXED_CANDIDATE.start_threshold * 2
    timeline = fixed_hysteresis(motion_rows([low] * 10 + [high] * 5, 250))
    assert timeline[12]["predicted_state"] == "STOPPED"
    assert timeline[13]["predicted_state"] == "MOVING"


def test_stop_resume_timeline_has_two_transitions():
    low, high = FIXED_CANDIDATE.stop_threshold / 2, FIXED_CANDIDATE.start_threshold * 2
    timeline = fixed_hysteresis(motion_rows([high] * 3 + [low] * 10 + [high] * 5))
    assert [item["state"] for item in transitions(timeline)] == ["STOPPED", "MOVING"]


def test_false_stop_is_accounted_by_time():
    timeline = [{"timestamp_ns": 0, "predicted_state": "MOVING"},
                {"timestamp_ns": 1_000_000_000, "predicted_state": "STOPPED"},
                {"timestamp_ns": 3_000_000_000, "predicted_state": "MOVING"}]
    metrics = duration_metrics(timeline, "no-stop", {})
    assert metrics["false_stop_duration_ms"] == 2000
    assert metrics["maximum_continuous_false_stop_duration_ms"] == 2000
    assert metrics["false_stop_transitions"] == 1


def test_no_stop_scenario_is_explicitly_all_moving():
    assert truth_at(123, "no-stop", {}) == "MOVING"


def test_missing_stop_resume_markers_is_incomplete(tmp_path):
    path = tmp_path / "markers.jsonl"
    path.write_text(json.dumps({"captured_monotonic_ns": 1, "payload": {"label": "STOPPED"}}), encoding="utf-8")
    ground_truth, missing = parse_ground_truth(path, "stop-resume")
    assert ground_truth == {"STOPPED": 1}
    assert missing == ["RESUMED"]


def test_no_stop_does_not_infer_from_missing_markers(tmp_path):
    ground_truth, missing = parse_ground_truth(tmp_path / "absent.jsonl", "no-stop")
    assert ground_truth == {} and missing == []


def test_profile_actions_include_accept_freeze_and_unknown():
    timeline = [{"timestamp_ns": 100, "predicted_state": "MOVING"},
                {"timestamp_ns": 200, "predicted_state": "STOPPED"}]
    profiles = [{"captured_monotonic_ns": value} for value in (50, 150, 250)]
    rows, summary = simulate_profiles(profiles, timeline, "no-stop", {})
    assert [row["slice_action"] for row in rows] == ["UNKNOWN", "ACCEPT", "FREEZE"]
    assert summary["unknown_profiles"] == 1


def test_profile_at_resume_marker_remains_stationary():
    assert truth_at(200, "stop-resume", {"STOPPED": 100, "RESUMED": 200}) == "STOPPED"


def test_pass_and_fail_criteria():
    metrics = {"false_stop_transitions": 0, "false_resume_transitions": 0,
               "stop_detection_delay_ms": 1000, "resume_detection_delay_ms": 500,
               "correct_time_fraction": .95}
    slices = {"moving_ground_truth_profiles": 100, "stationary_ground_truth_profiles": 100,
              "moving_profiles_incorrectly_frozen": 2, "stationary_profiles_incorrectly_accepted": 10}
    assert criteria_result("stop-resume", metrics, slices, True)[1] == "PASS"
    metrics["stop_detection_delay_ms"] = 3001
    assert criteria_result("stop-resume", metrics, slices, True)[1] == "FAIL"


def test_incomplete_ground_truth_has_distinct_result():
    assert criteria_result("stop-resume", {}, {}, False) == ({}, "GROUND_TRUTH_INCOMPLETE")


def test_tuning_report_is_excluded_from_validation_totals(tmp_path):
    for key, role, result in ((TUNING_SESSION_KEY, "TUNING", "PASS"), ("new", "VALIDATION", "FAIL")):
        folder = tmp_path / key / "motion_validation"; folder.mkdir(parents=True)
        (folder / "validation_summary.json").write_text(json.dumps({
            "session_key": key, "dataset_role": role, "scenario": "no-stop",
            "overall_result": result, "metrics": {}, "lidar_slice_simulation": {}
        }), encoding="utf-8")
    result = summarize(tmp_path)
    assert len(result["reports"]) == 2
    assert result["validation_only"] == {"total": 1, "pass": 0, "fail": 1, "incomplete": 0}


def test_validation_module_has_no_tuning_dependency():
    import scripts.validate_camera_motion as validation
    assert "tune_camera_motion" not in validation.__dict__
