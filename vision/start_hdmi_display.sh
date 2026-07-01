#!/bin/sh
set -eu

cd /root/vision_webcam_test

pkill -f '[w]ebcam_stream.py' 2>/dev/null || true
pkill -f '[h]dmi_camera_display.py' 2>/dev/null || true

rm -f /tmp/hdmi_camera_display.log /tmp/hdmi_camera_display.pid

export DISPLAY="${DISPLAY:-:0}"
if [ -f /home/lckfb/.Xauthority ]; then
    export XAUTHORITY=/home/lckfb/.Xauthority
fi

nohup python3 -u hdmi_camera_display.py \
    --camera 9 \
    --width 640 \
    --height 480 \
    --fps 30 \
    --detector-backend sync \
    --detect-scale 0.5 \
    --smooth-alpha 1.0 \
    --hold-frames 0 \
    >/tmp/hdmi_camera_display.log 2>&1 </dev/null &

echo "$!" >/tmp/hdmi_camera_display.pid
sleep 1

echo "pid=$(cat /tmp/hdmi_camera_display.pid)"
ps -p "$(cat /tmp/hdmi_camera_display.pid)" -o pid=,comm=,args= || true
tail -n 40 /tmp/hdmi_camera_display.log || true
