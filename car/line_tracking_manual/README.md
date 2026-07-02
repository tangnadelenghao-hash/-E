# Line Tracking Manual Test

Manual-push line tracking test for the grayscale module.

## Wiring

- `AD0` -> `PB20`
- `AD1` -> `PA14`
- `AD2` -> `PB10`
- `OUT` -> `PA7`

The module uses the three address pins to scan eight grayscale channels through
one digital output pin. Motor outputs are intentionally disabled in this test.

## Output

The firmware prints one line over `DEBUG_UART`:

```text
raw=00111100 active=00111100 pos=0 state=CENTER
```

Use this while pushing the car by hand over the track.
