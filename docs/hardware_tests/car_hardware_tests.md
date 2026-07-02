# Car Hardware Tests

These tests bring up the car board in small steps. Keep the motor power path
disabled while running the line tracking and Bluetooth tests.

## Electrical Check

Before flashing code:

- Confirm the grayscale connector has GND on pin 1 and +5V on pin 2.
- Confirm AD0 -> PB20, AD1 -> PA14, AD2 -> PB10, and OUT -> PA7.
- Confirm Bluetooth pin 1 -> PB6, Bluetooth pin 2 -> PB7, pin 3 -> GND,
  and pin 4 -> +5V.
- Confirm the Bluetooth TX idle level is safe for the MCU IO voltage before
  connecting it to PB7.

Pass condition: no reversed power pins, no short between +5V and GND, and the
Bluetooth signal level is MCU-safe.

## Line Tracking Manual Test

Firmware: `car/line_tracking_manual`

Build:

```powershell
powershell -ExecutionPolicy Bypass -File tools/build_line_tracking_manual.ps1
```

Flash `build/line_tracking_manual/line_tracking_manual.out`, open the debug
UART, and push the car by hand over the track.

Expected output:

```text
raw=00111100 active=00111100 pos=0 state=CENTER
```

Checks:

- Cover each sensor position and confirm the matching bit changes.
- Push the car left of the line and confirm `state=LEFT`.
- Push the car right of the line and confirm `state=RIGHT`.
- Put the line under the middle sensors and confirm `state=CENTER`.
- Lift the sensors away from the line and confirm `state=LOST`.

## Bluetooth UART Test

Firmware: `car/bluetooth_uart_test`

Build:

```powershell
powershell -ExecutionPolicy Bypass -File tools/build_bluetooth_uart_test.ps1
```

Flash `build/bluetooth_uart_test/bluetooth_uart_test.out`, pair a phone with
the Bluetooth serial module, and open a 9600 baud serial terminal.

Expected output:

```text
BT READY
```

Command checks:

- Send `ping`; expect `pong`.
- Send `help`; expect the command list.
- Send `hello`; expect `echo:hello`.

If there is no response, confirm Bluetooth pin 1 -> PB6 and Bluetooth pin 2 ->
PB7 before trying a crossed RX/TX cable.

## Integration Test

Use the line tracking firmware first and record stable raw sensor patterns for
left, center, right, and lost states. Then use the Bluetooth firmware to confirm
phone-to-board communication. After both pass separately, the next firmware can
combine the two outputs and report:

```text
raw=00111100 active=00111100 pos=0 state=CENTER
```

Pass condition: the phone receives line tracking state changes while the car is
pushed by hand, and no motor command is generated.
