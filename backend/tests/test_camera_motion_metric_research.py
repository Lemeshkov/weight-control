import cv2
import numpy as np

from scripts.research_camera_motion_metrics import (
    ANALYSIS_WIDTH,
    candidate_is_ready,
    distribution,
    flow_metrics,
    foreground_metrics,
    ground_truth,
    image_metrics,
)


def textured_image():
    image = np.zeros((72, 128), np.uint8)
    for y in range(8, 68, 12):
        for x in range(8, 124, 12):
            cv2.circle(image, (x, y), 2, 220, -1)
    return image


def test_appearance_metrics_have_dataset_independent_units():
    metrics, gradient = image_metrics(textured_image())
    assert 0 <= metrics["brightness"] <= 1
    assert 0 <= metrics["contrast"] <= 1
    assert metrics["gradient_energy"] > 0
    assert gradient.shape == (72, 128)


def test_flow_is_normalized_by_frame_interval():
    previous = textured_image()
    current = cv2.warpAffine(previous, np.float32([[1, 0, 2], [0, 1, 0]]), (128, 72))
    _, gradient = image_metrics(current)
    fast = flow_metrics(previous, current, .2, gradient)
    slow = flow_metrics(previous, current, .4, gradient)
    assert fast["informative_flow_p75"] > slow["informative_flow_p75"] * 1.8


def test_spatial_metrics_are_bounded_ratios():
    previous = textured_image()
    current = np.roll(previous, 2, axis=1)
    _, gradient = image_metrics(current)
    result = flow_metrics(previous, current, .25, gradient)
    for field in ("active_pixel_ratio", "adaptive_active_pixel_ratio", "active_tile_ratio",
                  "changed_pixel_ratio", "motion_bbox_area", "motion_centroid_x", "motion_centroid_y"):
        assert 0 <= result[field] <= 1


def test_foreground_presence_uses_fixed_background_not_markers():
    background = np.zeros((50, 100), np.uint8)
    image = background.copy(); cv2.rectangle(image, (25, 10), (75, 40), 255, -1)
    result = foreground_metrics(image, background)
    assert result["foreground_area_ratio"] > .1
    assert .4 < result["foreground_centroid_x"] < .6
    assert not result["foreground_touches_edge"]


def test_ground_truth_scenarios_are_explicit():
    markers = {"VEHICLE_ENTERED": 50, "STOPPED": 100, "RESUMED": 200, "VEHICLE_EXITED": 250}
    assert ground_truth(150, "stop-resume", markers) == "STOPPED"
    assert ground_truth(150, "no-stop", markers) == "MOVING"
    assert ground_truth(25, "no-stop", markers) == "NO_VEHICLE"


def test_distribution_is_descriptive_and_does_not_create_threshold():
    result = distribution([1, 2, 3, 100])
    assert set(result) == {"count", "median", "p10", "p90"}
    assert result["median"] == 2.5


def test_candidate_requires_all_development_sessions():
    assert candidate_is_ready({"sessions_basic_pass": 3, "false_transitions": 0}, 3)
    assert not candidate_is_ready({"sessions_basic_pass": 1, "false_transitions": 0}, 3)
    assert not candidate_is_ready({"sessions_basic_pass": 3, "false_transitions": 1}, 3)


def test_research_scale_is_explicit_and_fixed():
    assert ANALYSIS_WIDTH == 256
