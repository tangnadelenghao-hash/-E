import argparse
import multiprocessing as mp
import queue
import re
import signal
import subprocess
import sys
import time

import webcam_stream


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Show USB camera frames on the HDMI desktop.")
    parser.add_argument("--camera", default="9", help="OpenCV camera index or device path, default: 9")
    parser.add_argument("--width", type=int, default=640, help="Capture width, default: 640")
    parser.add_argument("--height", type=int, default=480, help="Capture height, default: 480")
    parser.add_argument("--fps", type=int, default=30, help="Capture fps, default: 30")
    parser.add_argument("--detect-fps", type=float, default=30.0, help="Async rectangle detection fps, default: 30")
    parser.add_argument("--detect-scale", type=float, default=0.5, help="Detection resize scale 0-1, default: 0.5")
    parser.add_argument("--smooth-alpha", type=float, default=1.0, help="Rectangle smoothing alpha, default: 1.0")
    parser.add_argument("--hold-frames", type=int, default=0, help="Frames to hold last rectangle after a miss")
    parser.add_argument("--log-interval", type=float, default=2.0, help="Seconds between FPS log lines, default: 2")
    parser.add_argument(
        "--detector-backend",
        choices=("sync", "process", "thread"),
        default="sync",
        help="Run detection per displayed frame or in the background, default: sync",
    )
    parser.add_argument("--window-name", default="Taishan Pi Camera", help="OpenCV window title")
    parser.add_argument("--fullscreen", dest="fullscreen", action="store_true", help="Show as a fullscreen HDMI window")
    parser.add_argument("--no-fullscreen", dest="fullscreen", action="store_false", help="Show as a normal window")
    parser.add_argument("--no-detect", dest="detect", action="store_false", help="Disable rectangle detection")
    parser.set_defaults(fullscreen=True, detect=True)
    return parser.parse_args(argv)


def should_exit(key_code):
    key = int(key_code) & 0xFF
    return key in (27, ord("q"), ord("Q"))


def apply_camera_settings(cap, width, height, fps):
    import cv2

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
    cap.set(cv2.CAP_PROP_FPS, int(fps))


def parse_xrandr_current_size(output):
    match = re.search(r"\bcurrent\s+(\d+)\s+x\s+(\d+)", output or "")
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)))


def read_display_size():
    try:
        result = subprocess.run(
            ["xrandr", "--current"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return parse_xrandr_current_size(result.stdout)


def configure_window(window_name, fullscreen):
    import cv2

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    if fullscreen:
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        size = read_display_size()
        if size is not None:
            cv2.moveWindow(window_name, 0, 0)
            cv2.resizeWindow(window_name, size[0], size[1])


def _put_latest(output_queue, result):
    while True:
        try:
            output_queue.put_nowait(result)
            return True
        except queue.Full:
            try:
                output_queue.get_nowait()
            except queue.Empty:
                return False


def _process_detector_worker(input_queue, output_queue, stop_event, target_fps, detect_scale, smooth_alpha, hold_frames):
    smoother = webcam_stream.RectangleSmoother(alpha=smooth_alpha, hold_frames=hold_frames)
    min_interval = 1.0 / max(0.1, float(target_fps))
    last_detection_time = 0.0

    while not stop_event.is_set():
        try:
            frame = input_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        if frame is None:
            break

        now = time.monotonic()
        if now - last_detection_time < min_interval:
            continue
        last_detection_time = now

        try:
            result = webcam_stream.detect_black_rectangle_resized(frame, scale=detect_scale)
            result = smoother.update(result)
        except Exception:
            result = webcam_stream.DetectionResult(False, None, 0.0)

        _put_latest(output_queue, result)


class ProcessRectangleDetector:
    def __init__(self, target_fps=8, detect_scale=0.5, smooth_alpha=0.35, hold_frames=5):
        self.target_fps = max(0.1, float(target_fps))
        self.detect_scale = float(detect_scale)
        self.smooth_alpha = float(smooth_alpha)
        self.hold_frames = int(hold_frames)
        self._input_queue = mp.Queue(maxsize=1)
        self._output_queue = mp.Queue(maxsize=2)
        self._stop_event = mp.Event()
        self._process = None
        self._last_submit_time = None
        self._latest_result = webcam_stream.DetectionResult(False, None, 0.0)

    def start(self):
        if self._process is not None:
            return
        self._process = mp.Process(
            target=_process_detector_worker,
            args=(
                self._input_queue,
                self._output_queue,
                self._stop_event,
                self.target_fps,
                self.detect_scale,
                self.smooth_alpha,
                self.hold_frames,
            ),
            daemon=True,
        )
        self._process.start()

    def stop(self):
        self._stop_event.set()
        try:
            self._input_queue.put_nowait(None)
        except queue.Full:
            pass
        if self._process is not None:
            self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=1.0)
            self._process = None

    def submit(self, frame, now=None):
        now = time.monotonic() if now is None else float(now)
        min_interval = 1.0 / self.target_fps
        if self._last_submit_time is not None and now - self._last_submit_time < min_interval:
            return False

        if not _put_latest(self._input_queue, frame.copy()):
            return False

        self._last_submit_time = now
        return True

    def snapshot(self):
        while True:
            try:
                self._latest_result = self._output_queue.get_nowait()
            except queue.Empty:
                break
        return self._latest_result


def create_async_detector(args):
    if args.detector_backend == "sync":
        return None
    if args.detector_backend == "process":
        return ProcessRectangleDetector(
            target_fps=args.detect_fps,
            detect_scale=args.detect_scale,
            smooth_alpha=args.smooth_alpha,
            hold_frames=args.hold_frames,
        )
    smoother = webcam_stream.RectangleSmoother(alpha=args.smooth_alpha, hold_frames=args.hold_frames)
    return webcam_stream.AsyncRectangleDetector(
        target_fps=args.detect_fps,
        detect_scale=args.detect_scale,
        smoother=smoother,
    )


def run_display(args):
    import cv2

    camera = webcam_stream.parse_camera(args.camera)
    webcam_stream.configure_camera_for_fps(camera, args.fps)

    cap = cv2.VideoCapture(camera, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"Cannot open {webcam_stream.camera_label(camera)}", file=sys.stderr, flush=True)
        return 2

    apply_camera_settings(cap, args.width, args.height, args.fps)
    configure_window(args.window_name, args.fullscreen)

    fps_meter = webcam_stream.FrameRateMeter(alpha=0.2)
    detector = create_async_detector(args) if args.detect and args.detector_backend != "sync" else None
    smoother = webcam_stream.RectangleSmoother(alpha=args.smooth_alpha, hold_frames=args.hold_frames)
    if detector is not None:
        detector.start()
    stop_requested = False
    last_log_time = time.monotonic()

    def request_stop(_signum, _frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    print(f"Camera: {webcam_stream.camera_label(camera)}", flush=True)
    print("HDMI display is running. Press q or Esc in the camera window to exit.", flush=True)

    try:
        while not stop_requested:
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            current_fps = fps_meter.tick()
            if args.detect:
                if detector is None:
                    raw_detection = webcam_stream.detect_black_rectangle_fast_resized(frame, scale=args.detect_scale)
                    detection = smoother.update(raw_detection)
                else:
                    detector.submit(frame)
                    detection = detector.snapshot()
                label = "DETECTED" if detection.detected else "LOST"
            else:
                detection = webcam_stream.DetectionResult(False, None, 0.0)
                label = None

            webcam_stream.draw_detection_overlay(frame, detection, label=label, fps_value=current_fps)
            cv2.imshow(args.window_name, frame)
            now = time.monotonic()
            if current_fps is not None and args.log_interval > 0 and now - last_log_time >= args.log_interval:
                print(f"Display FPS {current_fps:.1f} detection={label or 'off'}", flush=True)
                last_log_time = now
            if should_exit(cv2.waitKey(1)):
                break
    finally:
        if detector is not None:
            detector.stop()
        cap.release()
        cv2.destroyWindow(args.window_name)

    return 0


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    return run_display(args)


if __name__ == "__main__":
    raise SystemExit(main())
