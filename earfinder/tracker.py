"""
EarFinder: locates a person's head in 3D using an Intel RealSense D455.

Coordinate frame (RealSense standard):
  x = right
  y = down
  z = forward (into scene)
  units = meters

The returned vector is the displacement from the camera origin to the
midpoint between the subject's ears — a good proxy for head center and
the target for acoustic beam steering.
"""

import numpy as np
import pyrealsense2 as rs
import mediapipe as mp

# MediaPipe Pose landmark indices for ears
_LEFT_EAR = 7
_RIGHT_EAR = 8


class EarFinder:
    """
    Streams 3D head-position vectors from a RealSense D455.

    Usage::

        with EarFinder() as ef:
            for vec in ef.stream():
                if vec is not None:
                    print(vec)  # [x, y, z] in meters

    Or for a single snapshot::

        with EarFinder() as ef:
            vec = ef.get_head_vector()
    """

    def __init__(
        self,
        serial: str | None = None,
        width: int = 848,
        height: int = 480,
        fps: int = 30,
        detection_confidence: float = 0.5,
        tracking_confidence: float = 0.5,
    ):
        self._pipeline = rs.pipeline()
        config = rs.config()

        if serial:
            config.enable_device(serial)

        config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
        config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)

        profile = self._pipeline.start(config)

        depth_sensor = profile.get_device().first_depth_sensor()
        self._depth_scale = depth_sensor.get_depth_scale()

        # Align depth frames to the color frame so pixel coords are shared
        self._align = rs.align(rs.stream.color)

        color_profile = profile.get_stream(rs.stream.color).as_video_stream_profile()
        self._intrinsics = color_profile.get_intrinsics()

        self._pose = mp.solutions.pose.Pose(
            model_complexity=1,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_head_vector(self) -> np.ndarray | None:
        """
        Capture one frame and return the head position vector.

        Returns:
            np.ndarray of shape (3,) — [x, y, z] in meters, or
            None if no person is detected or depth is unavailable.
        """
        frames = self._pipeline.wait_for_frames()
        aligned = self._align.process(frames)

        color_frame = aligned.get_color_frame()
        depth_frame = aligned.get_depth_frame()

        if not color_frame or not depth_frame:
            return None

        color_image = np.asanyarray(color_frame.get_data())
        depth_image = np.asanyarray(depth_frame.get_data())

        return self._locate_head(color_image, depth_image)

    def stream(self):
        """
        Generator that yields head position vectors continuously.

        Yields:
            np.ndarray of shape (3,) or None (when no person is visible).
        """
        while True:
            yield self.get_head_vector()

    def close(self):
        self._pipeline.stop()
        self._pose.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _locate_head(
        self, color_image: np.ndarray, depth_image: np.ndarray
    ) -> np.ndarray | None:
        h, w = color_image.shape[:2]

        # MediaPipe expects RGB; RealSense gives BGR
        results = self._pose.process(color_image[:, :, ::-1])

        if not results.pose_landmarks:
            return None

        lm = results.pose_landmarks.landmark
        left_ear = lm[_LEFT_EAR]
        right_ear = lm[_RIGHT_EAR]

        # Normalized → pixel coordinates, midpoint between ears
        px = int(((left_ear.x + right_ear.x) / 2) * w)
        py = int(((left_ear.y + right_ear.y) / 2) * h)
        px = np.clip(px, 0, w - 1)
        py = np.clip(py, 0, h - 1)

        depth_raw = depth_image[py, px]
        if depth_raw == 0:
            return None

        depth_m = depth_raw * self._depth_scale
        point = rs.rs2_deproject_pixel_to_point(self._intrinsics, [px, py], depth_m)
        return np.array(point, dtype=np.float32)
