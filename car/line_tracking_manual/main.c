#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "line_tracking_logic.h"
#include "ti_msp_dl_config.h"

#define LINE_TRACKING_ACTIVE_LOW false
#define LINE_TRACKING_SELECT_SETTLE_CYCLES (CPUCLK_FREQ / 20000U)
#define LINE_TRACKING_REPORT_DELAY_CYCLES  (CPUCLK_FREQ / 20U)

static void uart_send_char(UART_Regs *uart, uint8_t chr)
{
    DL_UART_transmitDataBlocking(uart, chr);
}

static void uart_send_string(UART_Regs *uart, const char *text)
{
    while (*text != '\0') {
        uart_send_char(uart, (uint8_t) *text);
        text++;
    }
}

static void write_gpio_pin(GPIO_Regs *port, uint32_t pin, bool value)
{
    if (value) {
        DL_GPIO_setPins(port, pin);
    } else {
        DL_GPIO_clearPins(port, pin);
    }
}

static void line_tracking_select_channel(uint8_t channel)
{
    uint8_t address = line_tracking_channel_address(channel);

    write_gpio_pin(LINE_TRACKING_AD0_PORT, LINE_TRACKING_AD0_PIN,
        (address & 0x01U) != 0U);
    write_gpio_pin(LINE_TRACKING_AD1_PORT, LINE_TRACKING_AD1_PIN,
        (address & 0x02U) != 0U);
    write_gpio_pin(LINE_TRACKING_AD2_PORT, LINE_TRACKING_AD2_PIN,
        (address & 0x04U) != 0U);
}

static uint8_t line_tracking_read_selected(void)
{
    return (DL_GPIO_readPins(LINE_TRACKING_OUT_PORT, LINE_TRACKING_OUT_PIN) &
               LINE_TRACKING_OUT_PIN) != 0U ?
               1U :
               0U;
}

static void line_tracking_read_all(
    uint8_t values[LINE_TRACKING_CHANNEL_COUNT])
{
    for (uint8_t channel = 0U; channel < LINE_TRACKING_CHANNEL_COUNT; channel++) {
        line_tracking_select_channel(channel);
        delay_cycles(LINE_TRACKING_SELECT_SETTLE_CYCLES);
        values[channel] = line_tracking_read_selected();
    }
}

static void format_bits(uint8_t mask, char output[LINE_TRACKING_CHANNEL_COUNT + 1U])
{
    for (uint8_t index = 0U; index < LINE_TRACKING_CHANNEL_COUNT; index++) {
        output[index] = (mask & (uint8_t) (1U << index)) != 0U ? '1' : '0';
    }

    output[LINE_TRACKING_CHANNEL_COUNT] = '\0';
}

static void print_line_tracking_status(
    uint8_t raw_mask, const LineTrackingResult *result)
{
    char raw_bits[LINE_TRACKING_CHANNEL_COUNT + 1U];
    char active_bits[LINE_TRACKING_CHANNEL_COUNT + 1U];
    char line[96];
    int length;

    format_bits(raw_mask, raw_bits);
    format_bits(result->active_mask, active_bits);
    length = snprintf(line, sizeof(line), "raw=%s active=%s pos=%d state=%s\r\n",
        raw_bits, active_bits, (int) result->position,
        line_tracking_state_name(result->state));

    if (length > 0) {
        uart_send_string(DEBUG_UART_INST, line);
    }
}

int main(void)
{
    uint8_t sensor_values[LINE_TRACKING_CHANNEL_COUNT];

    SYSCFG_DL_init();
    delay_cycles(CPUCLK_FREQ / 10U);
    uart_send_string(DEBUG_UART_INST, "line tracking manual test start\r\n");

    while (1) {
        uint8_t raw_mask;
        uint8_t active_mask;
        LineTrackingResult result;

        line_tracking_read_all(sensor_values);
        raw_mask = line_tracking_mask_from_values(sensor_values, false);
        active_mask =
            line_tracking_mask_from_values(sensor_values, LINE_TRACKING_ACTIVE_LOW);
        result = line_tracking_analyze(active_mask);
        print_line_tracking_status(raw_mask, &result);

        delay_cycles(LINE_TRACKING_REPORT_DELAY_CYCLES);
    }
}
