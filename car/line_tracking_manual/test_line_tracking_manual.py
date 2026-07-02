import pathlib
import re
import unittest


PROJECT_DIR = pathlib.Path(__file__).resolve().parent
SYSCFG = PROJECT_DIR / "line_tracking_manual.syscfg"
MAIN_C = PROJECT_DIR / "main.c"
LOGIC_H = PROJECT_DIR / "line_tracking_logic.h"
LOGIC_C = PROJECT_DIR / "line_tracking_logic.c"
BUILD_SCRIPT = PROJECT_DIR.parents[1] / "tools" / "build_line_tracking_manual.ps1"


def read_text(path):
    return path.read_text(encoding="utf-8")


class LineTrackingManualModuleTest(unittest.TestCase):
    def test_expected_module_files_exist(self):
        for path in (SYSCFG, MAIN_C, LOGIC_H, LOGIC_C, BUILD_SCRIPT):
            self.assertTrue(path.exists(), f"missing {path}")

    def test_syscfg_uses_gray_module_mux_pins(self):
        syscfg = read_text(SYSCFG)

        self.assertIn('"LINE_TRACKING"', syscfg)
        expected_pins = (
            ("AD0", "PB20"),
            ("AD1", "PA14"),
            ("AD2", "PB10"),
            ("OUT", "PA7"),
        )
        for name, pin in expected_pins:
            self.assertRegex(
                syscfg,
                rf'\$name\s*=\s*"{name}";[\s\S]*?pin\.\$assign\s*=\s*"{pin}";',
            )
        self.assertRegex(
            syscfg,
            r'\$name\s*=\s*"OUT";[\s\S]*?direction\s*=\s*"INPUT";',
        )
        self.assertNotIn("/ti/driverlib/ADC12", syscfg)

    def test_logic_maps_channels_to_address_bits(self):
        logic_c = read_text(LOGIC_C)

        self.assertIn("line_tracking_channel_address", logic_c)
        self.assertIn("return (uint8_t) (channel & 0x07U);", logic_c)

    def test_logic_estimates_position_without_motor_commands(self):
        logic_c = read_text(LOGIC_C)
        main_c = read_text(MAIN_C)

        self.assertRegex(logic_c, r"static\s+const\s+int8_t\s+weights")
        for weight in ("-7", "-5", "-3", "-1", "1", "3", "5", "7"):
            self.assertIn(weight, logic_c)
        self.assertIn("LINE_TRACKING_STATE_LEFT", logic_c)
        self.assertIn("LINE_TRACKING_STATE_RIGHT", logic_c)
        self.assertIn("LINE_TRACKING_STATE_CENTER", logic_c)
        self.assertNotRegex(main_c + logic_c, r"TB6612|PWMA|PWMB|AIN1|AIN2|BIN1|BIN2|DL_Timer")

    def test_main_reports_raw_bits_and_position_over_uart(self):
        main_c = read_text(MAIN_C)

        self.assertIn("line_tracking_read_all", main_c)
        self.assertIn("line_tracking_analyze", main_c)
        self.assertIn("DEBUG_UART_INST", main_c)
        self.assertIn("raw=", main_c)
        self.assertIn("pos=", main_c)
        self.assertIn("state=", main_c)


if __name__ == "__main__":
    unittest.main()
