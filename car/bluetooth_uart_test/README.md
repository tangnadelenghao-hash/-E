# Bluetooth UART Test

Bluetooth connector wiring from the extension board:

- Bluetooth pin 1 -> PB6, MCU UART TX
- Bluetooth pin 2 -> PB7, MCU UART RX
- Bluetooth pin 3 -> GND
- Bluetooth pin 4 -> +5V

The firmware uses 9600 8N1 for the first bring-up pass.

## Phone Test

1. Flash `bluetooth_uart_test.out`.
2. Pair the phone with the Bluetooth serial module.
3. Open a Bluetooth serial terminal at 9600 baud.
4. Confirm the terminal receives `BT READY`.
5. Send `ping` and confirm the board returns `pong`.
6. Send `help` and confirm the command list returns.
7. Send any other short text and confirm the board returns `echo:<text>`.

If the phone receives nothing, check that Bluetooth pin 1 is connected to PB6
and Bluetooth pin 2 is connected to PB7. If it still fails, swap RX/TX only
after confirming the module pin labels with a meter or logic analyzer.
