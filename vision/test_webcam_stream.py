import unittest
import pathlib
import queue
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import webcam_stream
import hdmi_camera_display


def _require_cv2_numpy():
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise unittest.SkipTest(f"OpenCV/NumPy unavailable: {exc}")
    return cv2, np


def _synthetic_target_frame(width=640, height=480):
    cv2, np = _require_cv2_numpy()
    frame = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(frame, (90, 70), (550, 410), (0, 0, 0), 28)
    center = (width // 2, height // 2)
    for radius in (45, 90, 135):
        cv2.circle(frame, center, radius, (0, 0, 255), 3)
    return frame


def _rotated_target_frame(width=640, height=480):
    cv2, np = _require_cv2_numpy()
    frame = np.full((height, width, 3), 255, dtype=np.uint8)
    rect = ((width // 2, height // 2), (380, 250), -17)
    box = cv2.boxPoints(rect).astype(np.int32)
    cv2.drawContours(frame, [box], 0, (0, 0, 0), 26)
    center = (width // 2, height // 2)
    for radius in (45, 90, 125):
        cv2.circle(frame, center, radius, (0, 0, 255), 3)
    return frame, box


def _target_with_connected_stand_frame(width=640, height=480):
    cv2, np = _require_cv2_numpy()
    frame = np.full((height, width, 3), 185, dtype=np.uint8)
    outer = np.array([[270, 50], [580, 60], [565, 205], [260, 190]], dtype=np.int32)
    inner = np.array([[288, 69], [559, 77], [548, 184], [281, 173]], dtype=np.int32)
    cv2.fillConvexPoly(frame, outer, (0, 0, 0))
    cv2.fillConvexPoly(frame, inner, (220, 220, 220))
    cv2.line(frame, (282, 187), (282, 335), (0, 0, 0), 12)
    center = tuple(inner.astype(np.float32).mean(axis=0).astype(int))
    for radius in (28, 55, 82):
        cv2.ellipse(frame, center, (radius, int(radius * 0.72)), -4, 0, 360, (80, 80, 80), 2)
    return frame, outer


class WebcamStreamHelpersTest(unittest.TestCase):
    def test_parse_camera_numeric_index(self):
        self.assertEqual(webcam_stream.parse_camera("9"), 9)

    def test_parse_camera_device_path(self):
        self.assertEqual(webcam_stream.parse_camera("/dev/video9"), "/dev/video9")

    def test_index_from_video_path(self):
        self.assertEqual(webcam_stream.camera_label("/dev/video9"), "/dev/video9")
        self.assertEqual(webcam_stream.camera_label(9), "/dev/video9")

    def test_camera_device_path_for_v4l2_controls(self):
        self.assertEqual(webcam_stream.camera_device_path(9), "/dev/video9")
        self.assertEqual(webcam_stream.camera_device_path("/dev/video9"), "/dev/video9")
        self.assertIsNone(webcam_stream.camera_device_path("rtsp://example/camera"))

    def test_configure_camera_for_fps_disables_exposure_frame_drops(self):
        calls = []

        def fake_runner(args, **kwargs):
            calls.append(args)

            class Result:
                returncode = 0

            return Result()

        applied = webcam_stream.configure_camera_for_fps(9, runner=fake_runner)

        self.assertTrue(applied)
        self.assertEqual(calls[0][0], "v4l2-ctl")
        self.assertIn("-d", calls[0])
        self.assertIn("/dev/video9", calls[0])
        self.assertIn("--set-ctrl=exposure_auto_priority=0", calls[0])

    def test_html_references_mjpeg_endpoint(self):
        html = webcam_stream.build_index_html("/dev/video9", 8081)
        self.assertIn("/stream.mjpg", html)
        self.assertIn("/dev/video9", html)
        self.assertIn("8081", html)

    def test_request_shutdown_sets_stop_event_and_exits(self):
        stop_event = threading.Event()

        with self.assertRaises(SystemExit):
            webcam_stream.request_shutdown(stop_event)

        self.assertTrue(stop_event.is_set())

    def test_detection_is_enabled_by_default_and_can_be_disabled(self):
        default_args = webcam_stream.parse_args([])
        disabled_args = webcam_stream.parse_args(["--no-detect"])

        self.assertTrue(default_args.detect)
        self.assertFalse(disabled_args.detect)

    def test_detect_black_rectangle_from_synthetic_target(self):
        frame = _synthetic_target_frame()

        result = webcam_stream.detect_black_rectangle(frame)

        self.assertTrue(result.detected)
        self.assertEqual(result.corners.shape, (4, 2))
        xs = result.corners[:, 0]
        ys = result.corners[:, 1]
        self.assertLess(abs(xs.min() - 90), 18)
        self.assertLess(abs(xs.max() - 550), 18)
        self.assertLess(abs(ys.min() - 70), 18)
        self.assertLess(abs(ys.max() - 410), 18)

    def test_scaled_detection_returns_full_size_coordinates(self):
        frame = _synthetic_target_frame()

        result = webcam_stream.detect_black_rectangle_resized(frame, scale=0.5)

        self.assertTrue(result.detected)
        xs = result.corners[:, 0]
        ys = result.corners[:, 1]
        self.assertLess(abs(xs.min() - 90), 24)
        self.assertLess(abs(xs.max() - 550), 24)
        self.assertLess(abs(ys.min() - 70), 24)
        self.assertLess(abs(ys.max() - 410), 24)

    def test_fast_detection_handles_rotated_target(self):
        cv2, np = _require_cv2_numpy()
        frame, expected_box = _rotated_target_frame()

        result = webcam_stream.detect_black_rectangle_fast(frame)

        self.assertTrue(result.detected)
        expected_area = cv2.contourArea(expected_box.astype(np.float32))
        self.assertGreater(result.area, expected_area * 0.75)
        self.assertLess(result.area, expected_area * 1.35)
        expected_center = expected_box.astype(np.float32).mean(axis=0)
        actual_center = result.corners.astype(np.float32).mean(axis=0)
        self.assertLess(float(np.linalg.norm(expected_center - actual_center)), 20.0)

    def test_fast_scaled_detection_returns_full_size_coordinates(self):
        frame, _ = _rotated_target_frame()

        result = webcam_stream.detect_black_rectangle_fast_resized(frame, scale=0.5)

        self.assertTrue(result.detected)
        self.assertEqual(result.corners.shape, (4, 2))
        self.assertIsNotNone(result.inner_corners)
        self.assertEqual(result.inner_corners.shape, (4, 2))

    def test_fast_detection_handles_target_connected_to_stand(self):
        cv2, np = _require_cv2_numpy()
        frame, expected_outer = _target_with_connected_stand_frame()

        result = webcam_stream.detect_black_rectangle_fast(frame)

        self.assertTrue(result.detected)
        self.assertIsNotNone(result.inner_corners)
        expected_center = expected_outer.astype(np.float32).mean(axis=0)
        actual_center = result.corners.astype(np.float32).mean(axis=0)
        self.assertLess(float(np.linalg.norm(expected_center - actual_center)), 35.0)
        self.assertGreater(result.area, cv2.contourArea(expected_outer.astype(np.float32)) * 0.65)
        self.assertLess(cv2.contourArea(result.inner_corners.astype(np.float32)), result.area)

    def test_draw_detection_overlay_paints_inner_red_outline(self):
        cv2, np = _require_cv2_numpy()
        frame = np.full((480, 640, 3), 255, dtype=np.uint8)
        cv2.rectangle(frame, (90, 70), (550, 410), (0, 0, 0), 28)
        result = webcam_stream.detect_black_rectangle_fast(frame)

        overlay = webcam_stream.draw_detection_overlay(frame.copy(), result)
        hsv = cv2.cvtColor(overlay, cv2.COLOR_BGR2HSV)
        red_mask_a = cv2.inRange(hsv, (0, 90, 90), (10, 255, 255))
        red_mask_b = cv2.inRange(hsv, (170, 90, 90), (179, 255, 255))
        red_mask = cv2.bitwise_or(red_mask_a, red_mask_b)

        self.assertGreater(int(cv2.countNonZero(red_mask)), 500)

    def test_draw_detection_overlay_paints_green_outline(self):
        cv2, _ = _require_cv2_numpy()
        frame = _synthetic_target_frame()
        result = webcam_stream.detect_black_rectangle(frame)

        overlay = webcam_stream.draw_detection_overlay(frame.copy(), result)
        hsv = cv2.cvtColor(overlay, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(hsv, (45, 80, 80), (85, 255, 255))

        self.assertGreater(int(cv2.countNonZero(green_mask)), 1000)

    def test_draw_detection_overlay_paints_fps_at_top_right(self):
        cv2, np = _require_cv2_numpy()
        frame = np.zeros((120, 240, 3), dtype=np.uint8)
        result = webcam_stream.DetectionResult(False, None, 0.0)

        overlay = webcam_stream.draw_detection_overlay(frame.copy(), result, fps_value=24.6)
        changed = cv2.absdiff(frame, overlay)
        gray = cv2.cvtColor(changed, cv2.COLOR_BGR2GRAY)
        top_right_changed = cv2.countNonZero(gray[0:46, 130:240])
        left_changed = cv2.countNonZero(gray[0:46, 0:95])

        self.assertGreater(top_right_changed, 50)
        self.assertEqual(left_changed, 0)

    def test_frame_rate_meter_smooths_instantaneous_fps(self):
        meter = webcam_stream.FrameRateMeter(alpha=0.5)

        self.assertIsNone(meter.tick(10.0))
        self.assertAlmostEqual(meter.tick(10.1), 10.0, places=1)
        self.assertAlmostEqual(meter.tick(10.3), 7.5, places=1)

    def test_stream_delay_matches_requested_fps(self):
        self.assertAlmostEqual(webcam_stream.stream_delay_for_fps(30), 1.0 / 30.0, places=3)
        self.assertAlmostEqual(webcam_stream.stream_delay_for_fps(0), 1.0 / 30.0, places=3)

    def test_async_detector_updates_result_in_background(self):
        _, np = _require_cv2_numpy()
        frame = np.zeros((12, 12, 3), dtype=np.uint8)
        corners = np.array([[1, 1], [10, 1], [10, 10], [1, 10]], dtype=np.float32)

        def fake_detect(_frame, scale=1.0):
            return webcam_stream.DetectionResult(True, corners, 81.0)

        detector = webcam_stream.AsyncRectangleDetector(target_fps=30, detect_fn=fake_detect)
        try:
            detector.start()
            self.assertFalse(detector.snapshot().detected)
            self.assertTrue(detector.submit(frame, now=1.0))

            deadline = time.monotonic() + 1.0
            result = detector.snapshot()
            while not result.detected and time.monotonic() < deadline:
                time.sleep(0.01)
                result = detector.snapshot()

            self.assertTrue(result.detected)
            self.assertEqual(result.corners.shape, (4, 2))
        finally:
            detector.stop()

    def test_detect_black_rectangle_rejects_frame_edge_box(self):
        cv2, np = _require_cv2_numpy()
        frame = np.full((480, 640, 3), 255, dtype=np.uint8)
        cv2.rectangle(frame, (0, 0), (639, 479), (0, 0, 0), 24)

        result = webcam_stream.detect_black_rectangle(frame)

        self.assertFalse(result.detected)

    def test_detect_black_rectangle_when_dark_background_connects_to_frame_edge(self):
        cv2, np = _require_cv2_numpy()
        frame = np.full((480, 640, 3), 145, dtype=np.uint8)
        cv2.rectangle(frame, (0, 335), (639, 479), (45, 52, 62), -1)
        cv2.line(frame, (130, 0), (130, 479), (8, 8, 8), 18)

        outer = np.array([[170, 82], [504, 70], [520, 286], [154, 300]], dtype=np.int32)
        inner = np.array([[200, 110], [474, 101], [491, 257], [183, 270]], dtype=np.int32)
        cv2.fillConvexPoly(frame, outer, (0, 0, 0))
        cv2.fillConvexPoly(frame, inner, (232, 232, 232))
        cv2.fillConvexPoly(frame, np.array([[466, 250], [525, 248], [527, 293], [486, 292]], dtype=np.int32), (232, 232, 232))
        cv2.line(frame, (330, 0), (330, 88), (0, 0, 0), 14)
        for radius in (28, 55, 82):
            cv2.ellipse(frame, (337, 184), (radius, int(radius * 0.72)), -3, 0, 360, (0, 0, 180), 2)

        result = webcam_stream.detect_black_rectangle(frame)

        self.assertTrue(result.detected)
        xs = result.corners[:, 0]
        ys = result.corners[:, 1]
        self.assertLess(xs.min(), 185)
        self.assertGreater(xs.max(), 490)
        self.assertLess(ys.min(), 95)
        self.assertGreater(ys.max(), 275)

    def test_rectangle_smoother_keeps_recent_detection_during_short_loss(self):
        _, np = _require_cv2_numpy()
        corners = np.array([[90, 70], [550, 70], [550, 410], [90, 410]], dtype=np.float32)
        smoother = webcam_stream.RectangleSmoother(alpha=0.4, hold_frames=2)
        detected = webcam_stream.DetectionResult(True, corners, 123.0)
        lost = webcam_stream.DetectionResult(False, None, 0.0)

        first = smoother.update(detected)
        second = smoother.update(lost)
        third = smoother.update(lost)
        fourth = smoother.update(lost)

        self.assertTrue(first.detected)
        self.assertTrue(second.detected)
        self.assertTrue(third.detected)
        self.assertFalse(fourth.detected)


class HdmiCameraDisplayTest(unittest.TestCase):
    def test_hdmi_display_defaults_to_fullscreen_camera_9(self):
        args = hdmi_camera_display.parse_args([])

        self.assertEqual(args.camera, "9")
        self.assertEqual(args.width, 640)
        self.assertEqual(args.height, 480)
        self.assertEqual(args.fps, 30)
        self.assertEqual(args.detector_backend, "sync")
        self.assertEqual(args.detect_fps, 30.0)
        self.assertEqual(args.detect_scale, 0.5)
        self.assertEqual(args.smooth_alpha, 1.0)
        self.assertEqual(args.hold_frames, 0)
        self.assertEqual(args.log_interval, 2.0)
        self.assertTrue(args.fullscreen)
        self.assertTrue(args.detect)

    def test_hdmi_display_can_disable_fullscreen_and_detection(self):
        args = hdmi_camera_display.parse_args(["--no-fullscreen", "--no-detect"])

        self.assertFalse(args.fullscreen)
        self.assertFalse(args.detect)

    def test_exit_key_accepts_escape_q_or_upper_q(self):
        self.assertTrue(hdmi_camera_display.should_exit(27))
        self.assertTrue(hdmi_camera_display.should_exit(ord("q")))
        self.assertTrue(hdmi_camera_display.should_exit(ord("Q")))
        self.assertFalse(hdmi_camera_display.should_exit(ord("x")))

    def test_apply_camera_settings_sets_mjpg_resolution_and_fps(self):
        calls = []

        class FakeCapture:
            def set(self, prop, value):
                calls.append((prop, value))
                return True

        cv2, _ = _require_cv2_numpy()

        hdmi_camera_display.apply_camera_settings(FakeCapture(), 800, 600, 25)

        self.assertIn((cv2.CAP_PROP_FRAME_WIDTH, 800), calls)
        self.assertIn((cv2.CAP_PROP_FRAME_HEIGHT, 600), calls)
        self.assertIn((cv2.CAP_PROP_FPS, 25), calls)

    def test_parse_xrandr_current_size(self):
        output = "Screen 0: minimum 320 x 200, current 1440 x 900, maximum 8192 x 8192\n"

        self.assertEqual(hdmi_camera_display.parse_xrandr_current_size(output), (1440, 900))

    def test_parse_xrandr_current_size_returns_none_without_match(self):
        self.assertIsNone(hdmi_camera_display.parse_xrandr_current_size("no display"))

    def test_create_async_detector_returns_none_for_sync_backend(self):
        args = hdmi_camera_display.parse_args([])

        self.assertIsNone(hdmi_camera_display.create_async_detector(args))

    def test_create_async_detector_uses_process_backend_when_requested(self):
        args = hdmi_camera_display.parse_args(["--detector-backend", "process", "--detect-fps", "12", "--detect-scale", "0.5"])

        detector = hdmi_camera_display.create_async_detector(args)

        self.assertIsInstance(detector, hdmi_camera_display.ProcessRectangleDetector)
        self.assertEqual(detector.target_fps, 12.0)
        self.assertEqual(detector.detect_scale, 0.5)

    def test_create_async_detector_can_use_thread_backend(self):
        args = hdmi_camera_display.parse_args(["--detector-backend", "thread"])

        detector = hdmi_camera_display.create_async_detector(args)

        self.assertIsInstance(detector, webcam_stream.AsyncRectangleDetector)

    def test_put_latest_replaces_stale_queue_item(self):
        target = queue.Queue(maxsize=1)

        self.assertTrue(hdmi_camera_display._put_latest(target, "old"))
        self.assertTrue(hdmi_camera_display._put_latest(target, "new"))

        self.assertEqual(target.get_nowait(), "new")
        self.assertTrue(target.empty())


if __name__ == "__main__":
    unittest.main()
