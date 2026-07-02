import pathlib
import unittest


DOC = pathlib.Path(__file__).resolve().parent / "car_hardware_tests.md"


class CarHardwareTestPlan(unittest.TestCase):
    def test_test_plan_document_exists(self):
        self.assertTrue(DOC.exists(), f"missing {DOC}")

    def test_test_plan_covers_required_phases(self):
        text = DOC.read_text(encoding="utf-8")

        for heading in (
            "Electrical Check",
            "Line Tracking Manual Test",
            "Bluetooth UART Test",
            "Integration Test",
        ):
            self.assertIn(heading, text)

    def test_test_plan_records_expected_pins_and_outputs(self):
        text = DOC.read_text(encoding="utf-8")

        for item in (
            "AD0 -> PB20",
            "AD1 -> PA14",
            "AD2 -> PB10",
            "OUT -> PA7",
            "Bluetooth pin 1 -> PB6",
            "Bluetooth pin 2 -> PB7",
            "raw=",
            "state=",
            "BT READY",
            "ping",
            "pong",
        ):
            self.assertIn(item, text)


if __name__ == "__main__":
    unittest.main()
