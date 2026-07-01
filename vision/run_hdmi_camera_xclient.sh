#!/bin/sh
set -eu

cd /root/vision_webcam_test

export DISPLAY="${DISPLAY:-:0}"
export HOME=/root

python3 -u hdmi_camera_display.py \
    --camera 9 \
    --width 640 \
    --height 480 \
    --fps 30 \
    --detector-backend sync \
    --detect-scale 0.5 \
    --smooth-alpha 1.0 \
    --hold-frames 0 \
    >/tmp/hdmi_camera_display.log 2>&1
