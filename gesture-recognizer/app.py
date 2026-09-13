import json
import logging
import os
import subprocess
import time

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


RTSP_URL = os.getenv("RTSP_URL", "rtsp://127.0.0.1:8554/cam")
ANALYSIS_FPS = float(os.getenv("ANALYSIS_FPS", "5"))
MAX_WIDTH = int(os.getenv("MAX_WIDTH", "640"))
MIN_SCORE = float(os.getenv("GESTURE_MIN_SCORE", "0.65"))
ANNOTATED_RTSP_URL = os.getenv("ANNOTATED_RTSP_URL", "rtsp://127.0.0.1:8554/gestures")
ANNOTATED_CODEC = os.getenv("ANNOTATED_VIDEO_CODEC", "h264_v4l2m2m")
MODEL_PATH = "/models/gesture_recognizer.task"

HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("gesture-recognizer")


def event_for(result):
    hands = []
    for index, landmarks in enumerate(result.hand_landmarks):
        gesture = result.gestures[index][0] if result.gestures[index] else None
        handedness = result.handedness[index][0] if result.handedness[index] else None
        if gesture is None or gesture.category_name == "None" or gesture.score < MIN_SCORE:
            gesture_name = "None"
            gesture_score = 0.0
        else:
            gesture_name = gesture.category_name
            gesture_score = round(float(gesture.score), 3)

        # Normalized wrist and index-finger-tip coordinates enable lightweight tracking.
        hands.append(
            {
                "hand": handedness.category_name if handedness else "Unknown",
                "gesture": gesture_name,
                "score": gesture_score,
                "wrist": {"x": round(landmarks[0].x, 3), "y": round(landmarks[0].y, 3)},
                "index_tip": {"x": round(landmarks[8].x, 3), "y": round(landmarks[8].y, 3)},
            }
        )
    return hands


def open_capture():
    LOG.info("connecting to %s", RTSP_URL)
    capture = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


class AnnotatedPublisher:
    def __init__(self):
        self.process = None
        self.size = None

    def start(self, width, height):
        self.close()
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-re",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-video_size", f"{width}x{height}",
            "-framerate", str(ANALYSIS_FPS), "-i", "-", "-an",
            "-c:v", ANNOTATED_CODEC, "-b:v", "700k", "-g", "10",
            "-pix_fmt", "yuv420p", "-f", "rtsp", "-rtsp_transport", "tcp",
            ANNOTATED_RTSP_URL,
        ]
        LOG.info("starting annotated stream at %s (%s)", ANNOTATED_RTSP_URL, ANNOTATED_CODEC)
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE)
        self.size = (width, height)

    def write(self, frame):
        height, width = frame.shape[:2]
        if self.process is None or self.process.poll() is not None or self.size != (width, height):
            self.start(width, height)
        try:
            self.process.stdin.write(frame.tobytes())
            self.process.stdin.flush()
        except (BrokenPipeError, OSError):
            LOG.warning("annotated stream encoder stopped; it will be restarted")
            self.close()

    def close(self):
        if self.process is not None:
            if self.process.stdin:
                self.process.stdin.close()
            self.process.terminate()
            self.process.wait(timeout=3)
            self.process = None


def draw_overlay(frame, result, hands):
    height, width = frame.shape[:2]
    for index, landmarks in enumerate(result.hand_landmarks):
        points = [(round(item.x * width), round(item.y * height)) for item in landmarks]
        for start, end in HAND_CONNECTIONS:
            cv2.line(frame, points[start], points[end], (0, 220, 0), 2, cv2.LINE_AA)
        for point in points:
            cv2.circle(frame, point, 3, (0, 120, 255), -1, cv2.LINE_AA)

        hand = hands[index]
        text = f"{hand['hand']}: {hand['gesture']}"
        x, y = points[0]
        cv2.rectangle(frame, (x, max(0, y - 28)), (min(width, x + 245), y), (0, 0, 0), -1)
        cv2.putText(frame, text, (x + 5, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, "Gesture tracking", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)


def main():
    options = vision.GestureRecognizerOptions(
        base_options=python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    interval = 1.0 / max(ANALYSIS_FPS, 0.1)
    last_emit = None
    last_emit_at = 0.0
    publisher = AnnotatedPublisher()
    next_frame_at = 0.0

    with vision.GestureRecognizer.create_from_options(options) as recognizer:
        while True:
            capture = open_capture()
            if not capture.isOpened():
                LOG.warning("RTSP stream is unavailable; retrying in 3 seconds")
                capture.release()
                time.sleep(3)
                continue

            while True:
                ok, frame = capture.read()
                if not ok:
                    LOG.warning("RTSP frame read failed; reconnecting")
                    break

                now = time.monotonic()
                if now < next_frame_at:
                    continue
                next_frame_at = now + interval

                height, width = frame.shape[:2]
                if width > MAX_WIDTH:
                    new_height = round(height * MAX_WIDTH / width)
                    frame = cv2.resize(frame, (MAX_WIDTH, new_height), interpolation=cv2.INTER_AREA)

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = recognizer.recognize_for_video(image, int(time.monotonic() * 1000))
                hands = event_for(result)
                draw_overlay(frame, result, hands)
                publisher.write(frame)

                # Log changes and a periodic heartbeat while a hand remains visible.
                signature = json.dumps(hands, sort_keys=True)
                if hands and (signature != last_emit or now - last_emit_at >= 5):
                    print(json.dumps({"event": "gesture", "hands": hands, "ts": time.time()}), flush=True)
                    last_emit = signature
                    last_emit_at = now
                elif not hands and last_emit is not None:
                    print(json.dumps({"event": "hands_lost", "ts": time.time()}), flush=True)
                    last_emit = None

            capture.release()
            time.sleep(1)

    publisher.close()


if __name__ == "__main__":
    main()
