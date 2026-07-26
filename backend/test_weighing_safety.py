import unittest
from unittest.mock import Mock

from fastapi import HTTPException

from routers.weighing import (
    BRUTTO_TYPES,
    TARE_TYPES,
    commit_or_conflict,
    validate_weighing_payload,
)


class WeighingSafetyTests(unittest.TestCase):
    def test_valid_brutto_is_normalized(self):
        result = validate_weighing_payload(
            {
                "is_stable": True,
                "weight_type": "brutto",
                "weight": "12500",
                "plate_number": " а 123 вс ",
            },
            BRUTTO_TYPES,
        )
        self.assertEqual(result, ("BRUTTO", 12500.0, "А123ВС"))

    def test_unstable_measurement_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            validate_weighing_payload(
                {"is_stable": False, "weight_type": "TARE", "weight": 5000, "plate_number": "A1"},
                TARE_TYPES,
            )
        self.assertEqual(error.exception.status_code, 409)

    def test_wrong_measurement_type_is_rejected(self):
        with self.assertRaises(HTTPException):
            validate_weighing_payload(
                {"is_stable": True, "weight_type": "TARE", "weight": 5000, "plate_number": "A1"},
                BRUTTO_TYPES,
            )

    def test_non_positive_weight_is_rejected(self):
        with self.assertRaises(HTTPException):
            validate_weighing_payload(
                {"is_stable": True, "weight_type": "GROSS", "weight": 0, "plate_number": "A1"},
                BRUTTO_TYPES,
            )

    def test_commit_failure_rolls_back(self):
        db = Mock()
        db.commit.side_effect = RuntimeError("conflict")
        with self.assertRaises(HTTPException):
            commit_or_conflict(db, "conflict")
        db.rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
