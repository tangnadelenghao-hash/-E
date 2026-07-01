# Rectangle Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect the printed target's outer black rectangle on the RK3566 board and draw a stable green outline in the live web camera stream.

**Architecture:** Extend the existing `vision_webcam_test/webcam_stream.py` pipeline. Each captured frame will optionally run OpenCV black-frame detection, draw a green quadrilateral overlay when found, and use a small smoothing state so motion does not make the outline jump.

**Tech Stack:** Python 3, OpenCV, NumPy, standard-library HTTP MJPEG server, ADB for deployment.

---

### Task 1: Add Test-First Rectangle Detection

**Files:**
- Modify: `E:\My file\TI_cup_26\vision_webcam_test\test_webcam_stream.py`
- Modify: `E:\My file\TI_cup_26\vision_webcam_test\webcam_stream.py`

- [ ] **Step 1: Write failing tests**

Add tests that create a synthetic white frame with a thick black rectangular border and assert that `detect_black_rectangle(frame)` returns four corners and that `draw_detection_overlay(frame, result)` paints green pixels on the detected rectangle.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m unittest vision_webcam_test/test_webcam_stream.py`

Expected: FAIL because the detection helpers are not implemented.

- [ ] **Step 3: Implement detection helpers**

Add `DetectionResult`, `order_points`, `detect_black_rectangle`, `RectangleSmoother`, and `draw_detection_overlay`.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m unittest vision_webcam_test/test_webcam_stream.py`

Expected: PASS.

### Task 2: Integrate Detection Into Live Stream

**Files:**
- Modify: `E:\My file\TI_cup_26\vision_webcam_test\webcam_stream.py`
- Modify: `E:\My file\TI_cup_26\vision_webcam_test\test_webcam_stream.py`

- [ ] **Step 1: Write failing CLI test**

Assert `parse_args(["--no-detect"])` disables detection and default arguments enable detection.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m unittest vision_webcam_test/test_webcam_stream.py`

Expected: FAIL because the CLI flag is absent.

- [ ] **Step 3: Implement live overlay integration**

Add detection options to `parse_args` and call detection in `capture_loop` before JPEG encoding. Draw status text `DETECTED` or `LOST` in the frame.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m unittest vision_webcam_test/test_webcam_stream.py`

Expected: PASS.

### Task 3: Deploy and Verify on Board

**Files:**
- Deploy: `/root/vision_webcam_test/webcam_stream.py`
- Deploy: `/root/vision_webcam_test/test_webcam_stream.py`

- [ ] **Step 1: Confirm ADB and camera**

Run: ADB `devices`, `v4l2-ctl --list-devices`, and a one-frame OpenCV read from `/dev/video9`.

- [ ] **Step 2: Push files and run board tests**

Run: `adb push` for both files, then `cd /root/vision_webcam_test && python3 -m unittest test_webcam_stream.py`.

- [ ] **Step 3: Restart only the webcam test service**

Stop existing `webcam_stream.py` processes, start the new version on port `8081`, and set `adb forward tcp:8081 tcp:8081`.

- [ ] **Step 4: Verify web endpoints**

Request `/healthz`, `/`, and `/stream.mjpg` from `http://127.0.0.1:8081`.

Expected: health `OK`, index references `/stream.mjpg`, stream returns MJPEG bytes.
