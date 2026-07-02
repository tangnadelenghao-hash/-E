import pathlib
import re
import unittest


PROJECT_DIR = pathlib.Path(__file__).resolve().parent
SYSCFG = PROJECT_DIR / "bluetooth_uart_test.syscfg"
MAIN_C = PROJECT_DIR / "main.c"
README = PROJECT_DIR / "README.md"
BUILD_SCRIPT = PROJECT_DIR.parents[1] / "tools" / "build_bluetooth_uart_test.ps1"


def read_text(path):
    return path.read_text(encoding="utf-8")


class BluetoothUartTestModule(unittest.TestCase):
    def test_expected_files_exist(self):
        for path in (SYSCFG, MAIN_C, README, BUILD_SCRIPT):
            self.assertTrue(path.exists(), f"missing {path}")

    def test_syscfg_uses_bluetooth_connector_uart_pins(self):
        syscfg = read_text(SYSCFG)

        self.assertIn('"BLUETOOTH_UART"', syscfg)
        self.assertIn("targetBaudRate", syscfg)
        self.assertIn("9600", syscfg)
        self.assertRegex(syscfg, r'peripheral\.txPin\.\$assign\s*=\s*"PB6";')
        self.assertRegex(syscfg, r'peripheral\.rxPin\.\$assign\s*=\s*"PB7";')

    def test_firmware_announces_ready_and_echo_commands(self):
        main_c = read_text(MAIN_C)

        self.assertIn("BT READY", main_c)
        self.assertIn("ping", main_c)
        self.assertIn("pong", main_c)
        self.assertIn("help", main_c)
        self.assertIn("echo:", main_c)
        self.assertIn("DL_UART_receiveDataCheck", main_c)
        self.assertIn("DL_UART_transmitDataBlocking", main_c)

    def test_readme_contains_phone_test_steps(self):
        readme = read_text(README)

        for text in (
            "9600",
            "pin 1",
            "PB6",
            "pin 2",
            "PB7",
            "ping",
            "pong",
        ):
            self.assertIn(text, readme)


if __name__ == "__main__":
    unittest.main()
