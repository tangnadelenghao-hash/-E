#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "ti_msp_dl_config.h"

#define OLED_I2C_ADDRESS       (0x3CU)
#define OLED_WIDTH             (128U)
#define OLED_PAGES             (8U)
#define OLED_FIFO_PACKET_BYTES (8U)
#define OLED_PAYLOAD_BYTES     (OLED_FIFO_PACKET_BYTES - 1U)
#define OLED_I2C_TIMEOUT       (1000000U)

static uint32_t gI2CDelayCycles = 100U;

static bool i2c_wait_idle(void)
{
    uint32_t timeout = OLED_I2C_TIMEOUT;

    while (!(DL_I2C_getControllerStatus(OLED_I2C_INST) &
             DL_I2C_CONTROLLER_STATUS_IDLE)) {
        if (--timeout == 0U) {
            return false;
        }
    }

    return true;
}

static bool i2c_wait_not_busy(void)
{
    uint32_t timeout = OLED_I2C_TIMEOUT;

    while (DL_I2C_getControllerStatus(OLED_I2C_INST) &
           DL_I2C_CONTROLLER_STATUS_BUSY) {
        if (--timeout == 0U) {
            return false;
        }
    }

    return !(DL_I2C_getControllerStatus(OLED_I2C_INST) &
             DL_I2C_CONTROLLER_STATUS_ERROR);
}

static bool oled_i2c_write_packet(const uint8_t *packet, uint16_t length)
{
    if (!i2c_wait_idle()) {
        return false;
    }

    DL_I2C_flushControllerTXFIFO(OLED_I2C_INST);
    if (DL_I2C_fillControllerTXFIFO(OLED_I2C_INST, packet, length) != length) {
        return false;
    }

    DL_I2C_startControllerTransfer(OLED_I2C_INST, OLED_I2C_ADDRESS,
        DL_I2C_CONTROLLER_DIRECTION_TX, length);

    /*
     * MSPM0 SDK examples include this short delay as the I2C_ERR_13
     * workaround after starting a controller transfer.
     */
    delay_cycles(gI2CDelayCycles);

    if (!i2c_wait_not_busy()) {
        DL_I2C_flushControllerTXFIFO(OLED_I2C_INST);
        return false;
    }

    return i2c_wait_idle();
}

static bool oled_write_bytes(uint8_t control, const uint8_t *data, uint16_t length)
{
    uint8_t packet[OLED_FIFO_PACKET_BYTES];

    while (length > 0U) {
        uint16_t chunk = (length > OLED_PAYLOAD_BYTES) ? OLED_PAYLOAD_BYTES : length;

        packet[0] = control;
        memcpy(&packet[1], data, chunk);

        if (!oled_i2c_write_packet(packet, (uint16_t) (chunk + 1U))) {
            return false;
        }

        data += chunk;
        length -= chunk;
    }

    return true;
}

static bool oled_write_commands(const uint8_t *commands, uint16_t length)
{
    return oled_write_bytes(0x00U, commands, length);
}

static bool oled_write_data(const uint8_t *data, uint16_t length)
{
    return oled_write_bytes(0x40U, data, length);
}

static bool oled_set_cursor(uint8_t page, uint8_t column)
{
    const uint8_t commands[] = {
        (uint8_t) (0xB0U | (page & 0x07U)),
        (uint8_t) (0x00U | (column & 0x0FU)),
        (uint8_t) (0x10U | ((column >> 4U) & 0x0FU)),
    };

    return oled_write_commands(commands, sizeof(commands));
}

static bool oled_fill(uint8_t pattern)
{
    uint8_t line[OLED_PAYLOAD_BYTES];

    memset(line, pattern, sizeof(line));

    for (uint8_t page = 0U; page < OLED_PAGES; page++) {
        if (!oled_set_cursor(page, 0U)) {
            return false;
        }

        for (uint8_t column = 0U; column < OLED_WIDTH; column += OLED_PAYLOAD_BYTES) {
            uint16_t remaining = (uint16_t) (OLED_WIDTH - column);
            uint16_t chunk     = (remaining > OLED_PAYLOAD_BYTES) ? OLED_PAYLOAD_BYTES : remaining;

            if (!oled_write_data(line, chunk)) {
                return false;
            }
        }
    }

    return true;
}

static const uint8_t *font5x7(char c)
{
    static const uint8_t blank[5] = {0x00U, 0x00U, 0x00U, 0x00U, 0x00U};
    static const uint8_t d[5]     = {0x7FU, 0x41U, 0x41U, 0x22U, 0x1CU};
    static const uint8_t e[5]     = {0x7FU, 0x49U, 0x49U, 0x49U, 0x41U};
    static const uint8_t k[5]     = {0x7FU, 0x08U, 0x14U, 0x22U, 0x41U};
    static const uint8_t l[5]     = {0x7FU, 0x40U, 0x40U, 0x40U, 0x40U};
    static const uint8_t o[5]     = {0x3EU, 0x41U, 0x41U, 0x41U, 0x3EU};

    switch (c) {
        case 'D':
            return d;
        case 'E':
            return e;
        case 'K':
            return k;
        case 'L':
            return l;
        case 'O':
            return o;
        default:
            return blank;
    }
}

static bool oled_draw_char(uint8_t page, uint8_t column, char c)
{
    const uint8_t spacing = 0x00U;

    if (!oled_set_cursor(page, column)) {
        return false;
    }

    if (!oled_write_data(font5x7(c), 5U)) {
        return false;
    }

    return oled_write_data(&spacing, 1U);
}

static bool oled_draw_string(uint8_t page, uint8_t column, const char *text)
{
    while (*text != '\0') {
        if (!oled_draw_char(page, column, *text)) {
            return false;
        }

        column = (uint8_t) (column + 6U);
        text++;
    }

    return true;
}

static void oled_prepare_i2c_delay(void)
{
    DL_I2C_ClockConfig clockConfig;
    uint32_t clockSelFreq = 32000000U;

    DL_I2C_getClockConfig(OLED_I2C_INST, &clockConfig);

    if (clockConfig.clockSel == DL_I2C_CLOCK_MFCLK) {
        clockSelFreq = 4000000U;
    }

    gI2CDelayCycles =
        (3U * (clockConfig.divideRatio + 1U)) * (CPUCLK_FREQ / clockSelFreq);

    if (gI2CDelayCycles == 0U) {
        gI2CDelayCycles = 1U;
    }
}

static bool oled_init(void)
{
    const uint8_t initCommands[] = {
        0xAEU,       /* Display off */
        0xD5U, 0x80U,
        0xA8U, 0x3FU,
        0xD3U, 0x00U,
        0x40U,
        0x8DU, 0x14U,
        0x20U, 0x02U, /* Page addressing mode */
        0xA1U,
        0xC8U,
        0xDAU, 0x12U,
        0x81U, 0xCFU,
        0xD9U, 0xF1U,
        0xDBU, 0x40U,
        0xA4U,
        0xA6U,
        0x2EU,
        0xAFU,       /* Display on */
    };

    return oled_write_commands(initCommands, sizeof(initCommands));
}

int main(void)
{
    SYSCFG_DL_init();
    oled_prepare_i2c_delay();

    delay_cycles(CPUCLK_FREQ / 10U);

    if (oled_init()) {
        (void) oled_fill(0x00U);
        (void) oled_draw_string(3U, 43U, "OLED OK");

        if (oled_set_cursor(7U, 0U)) {
            for (uint8_t column = 0U; column < OLED_WIDTH; column += OLED_PAYLOAD_BYTES) {
                const uint8_t line[OLED_PAYLOAD_BYTES] = {
                    0x80U, 0x80U, 0x80U, 0x80U, 0x80U, 0x80U, 0x80U};
                uint16_t remaining = (uint16_t) (OLED_WIDTH - column);
                uint16_t chunk     = (remaining > OLED_PAYLOAD_BYTES) ?
                                         OLED_PAYLOAD_BYTES :
                                         remaining;

                (void) oled_write_data(line, chunk);
            }
        }
    }

    while (1) {
        __WFI();
    }
}
