#!/bin/sh
set -eu

LOG=/tmp/hdmi_camera_direct.log
APP_LOG=/tmp/hdmi_camera_display.log
PID_FILE=/tmp/hdmi_camera_display.pid

cd /root/vision_webcam_test

printf '%s\n' "Starting HDMI camera direct display" >"$LOG"

pkill -f '[w]ebcam_stream.py' 2>/dev/null || true
pkill -f '[h]dmi_camera_display.py' 2>/dev/null || true

rm -f "$APP_LOG" "$PID_FILE"
rm -f /tmp/.X0-lock

export DISPLAY=:0
unset XAUTHORITY

exec /usr/bin/xinit /root/vision_webcam_test/run_hdmi_camera_xclient.sh -- \
    /usr/bin/Xorg :0 vt7 -ac -nolisten tcp -s 0 -dpms -br >>"$LOG" 2>&1
