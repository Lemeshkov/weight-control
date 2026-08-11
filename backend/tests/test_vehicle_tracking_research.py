import numpy as np

from scripts.research_vehicle_tracking import (
    TrajectoryHysteresis,
    bbox_iou,
    dominant_trajectory_axis,
    lidar_slice_action,
    normalized_bbox_features,
    parse_yolo_boxes,
    select_detection,
    summarize_lidar_rows,
    track_continuity,
)


def box(x1, y1, x2, y2):
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "center_x": (x1+x2)/2,
            "center_y": (y1+y2)/2, "width": x2-x1, "height": y2-y1}


def test_detection_parsing_normalizes_bbox():
    rows = parse_yolo_boxes(np.array([[10, 20, 110, 220]]), np.array([.8]), np.array([7]), 200, 400)
    assert rows[0]["class_name"] == "truck"
    assert rows[0]["bbox_center_x"] == .3
    assert rows[0]["bbox_area"] == .25


def test_detection_parser_ignores_non_vehicle_class():
    assert parse_yolo_boxes([[0, 0, 10, 10]], [.9], [0], 100, 100) == []


def test_active_detection_prefers_largest_vehicle():
    assert select_detection([{"bbox_area": .1}, {"bbox_area": .4}])["bbox_area"] == .4


def test_track_continuity_reports_switch_and_temporary_loss():
    result = track_continuity([1, 1, None, None, 1, 2])
    assert result == {"visible_frames": 4, "unique_track_ids": 2, "track_switches": 1, "maximum_missing_run": 2}


def test_dominant_axis_is_not_assumed_to_be_x_or_y():
    axis = dominant_trajectory_axis([(0, 0), (1, 2), (2, 4), (3, 6)])
    assert axis[0] > 0 and axis[1] > 0
    assert abs(axis[1] / axis[0] - 2) < .1


def test_normalized_bbox_motion_contains_edges_scale_and_iou():
    result = normalized_bbox_features(box(.1, .1, .3, .3), box(.2, .2, .5, .5), .5, (0, 1))
    assert result["center_speed"] > 0
    assert result["leading_edge_velocity"] > result["trailing_edge_velocity"]
    assert result["scale_change_per_sec"] > 0
    assert 0 < result["bbox_iou"] < 1


def test_identical_boxes_have_unit_iou():
    value = box(.1, .1, .4, .4)
    assert bbox_iou(value, value) == 1


def test_hysteresis_requires_confirmation_for_stop_and_resume():
    fsm = TrajectoryHysteresis(.01, .05, 1000, 500)
    assert fsm.update(0, visible=True, speed=.2) == "MOVING"
    assert fsm.update(100_000_000, visible=True, speed=0) == "MOVING"
    assert fsm.update(1_200_000_000, visible=True, speed=0) == "STOPPED"
    assert fsm.update(1_300_000_000, visible=True, speed=.2) == "STOPPED"
    assert fsm.update(1_900_000_000, visible=True, speed=.2) == "MOVING"


def test_temporary_track_loss_is_not_stopped():
    fsm = TrajectoryHysteresis(.01, .05, 1000, 500)
    fsm.update(0, visible=True, speed=.2)
    assert fsm.update(1, visible=False, speed=None) == "TRACK_LOST"


def test_no_vehicle_is_not_stopped():
    fsm = TrajectoryHysteresis(.01, .05, 1000, 500)
    assert fsm.update(0, visible=False, speed=None) == "NO_VEHICLE"


def test_lidar_slice_mapping():
    assert {state: lidar_slice_action(state) for state in ("NO_VEHICLE", "MOVING", "STOPPED", "TRACK_LOST")} == {
        "NO_VEHICLE": "EXCLUDE", "MOVING": "ACCEPT", "STOPPED": "FREEZE", "TRACK_LOST": "UNKNOWN",
    }


def test_lidar_slice_summary_counts_unknown_track_loss():
    rows = [{"ground_truth_state": "NO_VEHICLE", "slice_action": "EXCLUDE"},
            {"ground_truth_state": "MOVING", "slice_action": "UNKNOWN"},
            {"ground_truth_state": "STOPPED", "slice_action": "UNKNOWN"}]
    assert summarize_lidar_rows(rows) == {"total_profiles": 3, "excluded_profiles": 1,
        "accepted_profiles": 0, "frozen_profiles": 0, "unknown_profiles": 2,
        "moving_profiles_incorrectly_frozen": 0, "stationary_profiles_incorrectly_accepted": 0}
