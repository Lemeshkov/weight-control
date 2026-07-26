import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.lidar_client import LidarClient


class LidarCalculationTests(unittest.TestCase):
    def make_client(self, floor_level=1526):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        config_path = Path(temp_dir.name) / "floor_config.json"
        config_path.write_text(
            json.dumps({"floor_level_mm": floor_level}),
            encoding="utf-8",
        )
        env_patch = patch.dict(
            os.environ,
            {"FLOOR_CONFIG_PATH": str(config_path)},
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)
        return LidarClient()

    def test_loads_calibrated_floor(self):
        self.assertEqual(self.make_client().FLOOR_LEVEL, 1526)

    def test_floor_only_scan_is_empty(self):
        client = self.make_client()
        result = client.analyze_scan_with_angles([1510, 1520, 1526, 1530] * 10)
        self.assertTrue(result["is_empty"])
        self.assertEqual(result["object_points"], [])
        self.assertEqual(result["background_level"], 1526)

    def test_dominant_object_is_not_mistaken_for_background(self):
        client = self.make_client()
        distances = [1515] * 20 + [1200] * 80 + [1525] * 20
        result = client.analyze_scan_with_angles(distances)
        self.assertFalse(result["is_empty"])
        self.assertEqual(len(result["object_points"]), 80)
        self.assertEqual(result["background_level"], 1526)
        self.assertEqual(result["object_height_mm"], 326)

    def test_output_range_uses_10000_angle_scale(self):
        client = self.make_client()
        client._send_raw = lambda command: (
            "sRA LMPoutputRange 1 1388 FFFEAA20 00055730"
        )
        result = client.get_current_angle_range()
        self.assertEqual(result["resolution_deg"], 0.5)
        self.assertAlmostEqual(result["start_angle_deg"], -8.752)
        self.assertEqual(result["stop_angle_deg"], 35.0)

    def test_dist1_metadata_is_not_parsed_as_distance(self):
        client = self.make_client()
        telegram = (
            "sRA LMDscandata DIST1 3F800000 00000000 FFF92230 "
            "00001388 00000003 000005DC 000004B0 000005F0 RSSI1"
        )
        self.assertEqual(client.parse_raw_data(telegram), [1500, 1200, 1520])
        geometry = client.get_scan_geometry(telegram)
        self.assertEqual(geometry["start_angle_deg"], -45.0)
        self.assertEqual(geometry["angular_step_deg"], 0.5)
        self.assertEqual(geometry["points_count"], 3)
        self.assertEqual(geometry["total_angle_deg"], 1.0)


if __name__ == "__main__":
    unittest.main()
