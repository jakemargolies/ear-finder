"""
EarFinder: locates a person's head in 3D using an Intel RealSense D455.

Coordinate frame (RealSense standard):
  x = right
  y = down
  z = forward (into scene)
  units = meters

The returned vector is the displacement from the camera origin to the
midpoint between the subject's ears, which I'm considering a good proxy
for head center and the target for acoustic beam steering.

macOS note: pyrealsense2 cannot claim the D455 color camera interface because
macOS's UVC kernel driver holds it exclusively. This module uses the left
infrared (IR) stream instead — it is on the same USB interface as depth,
requires no special permissions, and is already synchronized and aligned with
the depth frame. MediaPipe receives the grayscale IR image converted to 3-channel.
"""

import pathlib
import cv2
import numpy as np
import pyrealsense2 as rs
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

_LEFT_EAR = 7
_RIGHT_EAR = 8

_DEFAULT_MODEL = pathlib.Path(__file__).parent.parent / "pose_landmarker.task"


class EarFinder:
    """
    Streams 3D head-position vectors from a RealSense D455.

    Usage::

        with EarFinder() as ef:
            for vec in ef.stream():
                if vec is not None:
                    print(vec)  # [x, y, z] in meters

        # With live annotated video:
        with EarFinder() as ef:
            for vec, frame in ef.stream_visual():
                cv2.imshow("ear-finder", frame)
                cv2.waitKey(30)
    """

    def __init__(
        self,
        serial: str | None = None,
        width: int = 848,
        height: int = 480,
        fps: int = 30,
        model_path: str | pathlib.Path | None = None,
        detection_confidence: float = 0.5,
        tracking_confidence: float = 0.5,
    ):
        self._pipeline = rs.pipeline()
        rs_config = rs.config()
        if serial:
            rs_config.enable_device(serial)
        rs_config.enable_stream(rs.stream.infrared, 1, width, height, rs.format.y8, fps)
        rs_config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)

        profile = self._pipeline.start(rs_config)
        depth_sensor = profile.get_device().first_depth_sensor()
        self._depth_scale = depth_sensor.get_depth_scale()

        depth_stream = profile.get_stream(rs.stream.depth).as_video_stream_profile()
        self._intrinsics = depth_stream.get_intrinsics()

        # Align depth to the IR frame so pixel coords are shared.
        self._align = rs.align(rs.stream.infrared)

        model = pathlib.Path(model_path) if model_path else _DEFAULT_MODEL
        if not model.exists():
            raise FileNotFoundError(
                f"Pose landmarker model not found at {model}. "
                "Download it with:\n"
                "  curl -L -o pose_landmarker.task "
                "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
                "pose_landmarker_full/float16/latest/pose_landmarker_full.task"
            )

        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model)),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=detection_confidence,
            min_pose_presence_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        self._timestamp_ms = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_head_vector(self) -> np.ndarray | None:
        color_image, depth_image = self._get_frames()
        if color_image is None:
            return None
        vec, *_ = self._process_frame(color_image, depth_image)
        return vec

    def get_visual_frame(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        color_image, depth_image = self._get_frames()
        if color_image is None:
            return None, None
        vec, lx, ly, rx, ry, mx, my = self._process_frame(color_image, depth_image)
        return vec, self._annotate(color_image, vec, lx, ly, rx, ry, mx, my)

    def stream(self):
        """Yields head position vectors (np.ndarray [x,y,z] or None) continuously."""
        while True:
            yield self.get_head_vector()

    def stream_visual(self):
        """Yields (vec, annotated_bgr_frame) continuously."""
        while True:
            color_image, depth_image = self._get_frames()
            if color_image is None:
                continue
            vec, lx, ly, rx, ry, mx, my = self._process_frame(color_image, depth_image)
            yield vec, self._annotate(color_image, vec, lx, ly, rx, ry, mx, my)

    def close(self):
        self._pipeline.stop()
        self._landmarker.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_frames(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        frames = self._pipeline.wait_for_frames()
        aligned = self._align.process(frames)
        ir_frame = aligned.get_infrared_frame(1)
        depth_frame = aligned.get_depth_frame()
        if not ir_frame or not depth_frame:
            return None, None
        ir = np.asanyarray(ir_frame.get_data())
        # Blur removes the IR projector dot pattern before MediaPipe sees it.
        ir_smooth = cv2.GaussianBlur(ir, (7, 7), 0)
        bgr = cv2.cvtColor(ir_smooth, cv2.COLOR_GRAY2BGR)
        return bgr, np.asanyarray(depth_frame.get_data())

    def _process_frame(self, color_image: np.ndarray, depth_image: np.ndarray) -> tuple:
        h, w = color_image.shape[:2]
        rgb = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._timestamp_ms += 1
        result = self._landmarker.detect_for_video(mp_image, self._timestamp_ms)

        if not result.pose_landmarks:
            return None, None, None, None, None, None, None

        lm = result.pose_landmarks[0]
        left_ear = lm[_LEFT_EAR]
        right_ear = lm[_RIGHT_EAR]

        lx = int(np.clip(left_ear.x * w, 0, w - 1))
        ly = int(np.clip(left_ear.y * h, 0, h - 1))
        rx = int(np.clip(right_ear.x * w, 0, w - 1))
        ry = int(np.clip(right_ear.y * h, 0, h - 1))
        mx = int(np.clip((lx + rx) / 2, 0, w - 1))
        my = int(np.clip((ly + ry) / 2, 0, h - 1))

        depth_raw = depth_image[my, mx]
        if depth_raw == 0:
            return None, lx, ly, rx, ry, mx, my

        depth_m = depth_raw * self._depth_scale
        point = rs.rs2_deproject_pixel_to_point(self._intrinsics, [mx, my], depth_m)
        return np.array(point, dtype=np.float32), lx, ly, rx, ry, mx, my

    def _annotate(self, color_image, vec, lx, ly, rx, ry, mx, my) -> np.ndarray:
        frame = color_image.copy()

        if lx is not None:
            cv2.circle(frame, (lx, ly), 7, (255, 255, 0), -1)
            cv2.circle(frame, (rx, ry), 7, (255, 255, 0), -1)
            cv2.line(frame, (lx, ly), (rx, ry), (255, 255, 0), 1)
            cv2.circle(frame, (mx, my), 14, (0, 255, 0), 2)
            cv2.drawMarker(frame, (mx, my), (0, 255, 0), cv2.MARKER_CROSS, 24, 2)

        if vec is not None:
            label = f"x={vec[0]:+.3f}  y={vec[1]:+.3f}  z={vec[2]:+.3f} m"
            cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        elif lx is not None:
            cv2.putText(frame, "no depth at midpoint", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
        else:
            cv2.putText(frame, "no detection", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        return frame
