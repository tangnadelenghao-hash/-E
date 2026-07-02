#include "line_tracking_logic.h"

uint8_t line_tracking_channel_address(uint8_t channel)
{
    return (uint8_t) (channel & 0x07U);
}

uint8_t line_tracking_mask_from_values(
    const uint8_t values[LINE_TRACKING_CHANNEL_COUNT], bool active_low)
{
    uint8_t mask = 0U;

    for (uint8_t index = 0U; index < LINE_TRACKING_CHANNEL_COUNT; index++) {
        bool high = values[index] != 0U;
        bool active = active_low ? !high : high;

        if (active) {
            mask |= (uint8_t) (1U << index);
        }
    }

    return mask;
}

LineTrackingResult line_tracking_analyze(uint8_t active_mask)
{
    static const int8_t weights[LINE_TRACKING_CHANNEL_COUNT] = {
        -7, -5, -3, -1, 1, 3, 5, 7,
    };
    LineTrackingResult result = {
        .active_mask = active_mask,
        .active_count = 0U,
        .position = 0,
        .state = LINE_TRACKING_STATE_LOST,
    };
    int16_t weighted_sum = 0;

    for (uint8_t index = 0U; index < LINE_TRACKING_CHANNEL_COUNT; index++) {
        if ((active_mask & (uint8_t) (1U << index)) != 0U) {
            weighted_sum += weights[index];
            result.active_count++;
        }
    }

    if (result.active_count == 0U) {
        return result;
    }

    result.position = (int8_t) (weighted_sum / (int16_t) result.active_count);

    if (result.position <= -2) {
        result.state = LINE_TRACKING_STATE_LEFT;
    } else if (result.position >= 2) {
        result.state = LINE_TRACKING_STATE_RIGHT;
    } else {
        result.state = LINE_TRACKING_STATE_CENTER;
    }

    return result;
}

const char *line_tracking_state_name(LineTrackingState state)
{
    switch (state) {
        case LINE_TRACKING_STATE_LEFT:
            return "LEFT";
        case LINE_TRACKING_STATE_CENTER:
            return "CENTER";
        case LINE_TRACKING_STATE_RIGHT:
            return "RIGHT";
        case LINE_TRACKING_STATE_LOST:
        default:
            return "LOST";
    }
}
