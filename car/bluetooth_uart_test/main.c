#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "ti_msp_dl_config.h"

#define COMMAND_BUFFER_SIZE 48U
#define LOOP_DELAY_CYCLES   (CPUCLK_FREQ / 1000U)
#define READY_PERIOD_TICKS  1000U

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

static void bluetooth_send_ready(void)
{
    uart_send_string(BLUETOOTH_UART_INST, "BT READY\r\n");
}

static void bluetooth_send_help(void)
{
    uart_send_string(BLUETOOTH_UART_INST,
        "commands: ping, help, echo text\r\n");
}

static void bluetooth_handle_command(const char *command)
{
    if (command[0] == '\0') {
        return;
    }

    if (strcmp(command, "ping") == 0) {
        uart_send_string(BLUETOOTH_UART_INST, "pong\r\n");
    } else if (strcmp(command, "help") == 0) {
        bluetooth_send_help();
    } else {
        uart_send_string(BLUETOOTH_UART_INST, "echo:");
        uart_send_string(BLUETOOTH_UART_INST, command);
        uart_send_string(BLUETOOTH_UART_INST, "\r\n");
    }
}

static void bluetooth_poll_command(char *buffer, uint8_t *length)
{
    uint8_t received;

    if (!DL_UART_receiveDataCheck(BLUETOOTH_UART_INST, &received)) {
        return;
    }

    if ((received == '\r') || (received == '\n')) {
        buffer[*length] = '\0';
        bluetooth_handle_command(buffer);
        *length = 0U;
        return;
    }

    if (*length < (COMMAND_BUFFER_SIZE - 1U)) {
        buffer[*length] = (char) received;
        (*length)++;
    } else {
        *length = 0U;
        uart_send_string(BLUETOOTH_UART_INST, "ERR command too long\r\n");
    }
}

int main(void)
{
    char command_buffer[COMMAND_BUFFER_SIZE];
    uint8_t command_length = 0U;
    uint16_t ready_ticks = 0U;

    SYSCFG_DL_init();
    delay_cycles(CPUCLK_FREQ / 10U);
    bluetooth_send_ready();
    bluetooth_send_help();

    while (1) {
        bluetooth_poll_command(command_buffer, &command_length);

        ready_ticks++;
        if (ready_ticks >= READY_PERIOD_TICKS) {
            ready_ticks = 0U;
            bluetooth_send_ready();
        }

        delay_cycles(LOOP_DELAY_CYCLES);
    }
}
