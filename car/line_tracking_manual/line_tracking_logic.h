#ifndef LINE_TRACKING_LOGIC_H
#define LINE_TRACKING_LOGIC_H

#include <stdbool.h>
#include <stdint.h>

#define LINE_TRACKING_CHANNEL_COUNT 8U

typedef enum {
    LINE_TRACKING_STATE_LOST = 0,
    LINE_TRACKING_STATE_LEFT,
    LINE_TRACKING_STATE_CENTER,
    LINE_TRACKING_STATE_RIGHT,
} LineTrackingState;

typedef struct {
    uint8_t active_mask;
    uint8_t active_count;
    int8_t position;
    LineTrackingState state;
} LineTrackingResult;

uint8_t line_tracking_channel_address(uint8_t channel);
uint8_t line_tracking_mask_from_values(
    const uint8_t values[LINE_TRACKING_CHANNEL_COUNT], bool active_low);
LineTrackingResult line_tracking_analyze(uint8_t active_mask);
const char *line_tracking_state_name(LineTrackingState state);

#endif
