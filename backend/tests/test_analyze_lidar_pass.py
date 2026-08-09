from scripts.analyze_lidar_pass import analyze_document, compare_profiles


def test_analyze_document_calculates_effective_frequency_and_deltas():
    document = {
        "profiles": [
            {
                "captured_at": "2026-08-09T10:00:00+00:00",
                "sequence_number": 10,
                "points_total": 4,
                "points_valid": 3,
                "distances_mm": [1000, 1100, 1200],
            },
            {
                "captured_at": "2026-08-09T10:00:00.300000+00:00",
                "sequence_number": 11,
                "points_total": 4,
                "points_valid": 3,
                "distances_mm": [1010, 1110, 1210],
            },
        ]
    }

    summary, rows = analyze_document(document)

    assert summary["profiles_count"] == 2
    assert summary["duration_seconds"] == 0.3
    assert summary["effective_frequency_hz"] == 3.333333
    assert summary["geometry_reconstructable"] is False
    assert rows[1]["delta_time_ms"] == 300.0
    assert rows[1]["median_abs_delta_mm"] == 10.0


def test_compare_profiles_resamples_different_point_counts():
    result = compare_profiles([100, 200, 300], [100, 300])

    assert result["comparison_points"] == 2
    assert result["rmse_mm"] == 0.0
    assert result["correlation"] == 1.0
