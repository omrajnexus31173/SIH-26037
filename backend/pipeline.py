"""Real camera perception -> tracking -> drivable area -> planning -> safety.

The exact same AdaptivePlanner and SafetyMonitor classes are used by the
simulation engine. For an uncalibrated camera, planner coordinates and safety
distances are explicitly labelled as image-plane/perspective proxies; no metric
distance accuracy is claimed.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from backend.config import settings
from backend.perception.calibration import CalibrationManager
from backend.perception.detector import DetectorResult, UltralyticsDetector, YoloOnnxDetector
from backend.perception.labels import OBSTACLE_CLASSES, TRAFFIC_CONTROL_CLASSES, VEHICLE_CLASSES, VULNERABLE_CLASSES
from backend.perception.types import Detection
from backend.planning.planner import AdaptivePlanner
from backend.planning.types import Obstacle
from backend.safety.safety import SafetyMonitor
from backend.segmentation.road import RoadSegmentation, TwinLiteNetSegmenter
from backend.tracking.tracker import CentroidTracker, Track
from backend.utils import clamp, now_iso

FRAME_WIDTH, FRAME_HEIGHT = 640, 360


@dataclass
class PipelineResult:
    data: Dict[str, Any]
    annotated: np.ndarray


class PerceptionPipeline:
    def __init__(self):
        self.detector_backend = settings.detector_backend
        if self.detector_backend == "ultralytics":
            self.detector = UltralyticsDetector(
                model_path=str(settings.model_dir / "yolov8n.pt"),
                conf_threshold=settings.conf_threshold,
                iou_threshold=settings.iou_threshold,
                use_cuda=settings.use_cuda,
            )
        else:
            self.detector = YoloOnnxDetector(
                model_path=settings.yolo_model,
                conf_threshold=settings.conf_threshold,
                iou_threshold=settings.iou_threshold,
                use_cuda=settings.use_cuda,
            )
        self.segmenter = TwinLiteNetSegmenter(settings.segmentation_model, use_cuda=settings.use_cuda)
        self.tracker = CentroidTracker()
        # Uncalibrated perspective grid units, NOT metres.
        self.planner = AdaptivePlanner(x_min=-8.0, x_max=8.0, y_max=30.0,
                                       resolution=0.5, inflation=0.55,
                                       prediction_horizon=1.0)
        self.safety = SafetyMonitor()
        self.last_result: Optional[Dict[str, Any]] = None
        self.last_annotated: Optional[np.ndarray] = None
        # TwinLiteNet is real but the CPU inference is heavier than YOLO. It runs
        # every third processed frame; the most recent real mask is reused in the
        # intervening frames and explicitly reported as cached.
        self.segmentation_interval = 3
        self._seg_counter = 0
        self._last_seg: Optional[RoadSegmentation] = None
        self.overlay_config: Dict[str, bool] = {
            "detections": True, "segmentation": True, "path": True,
            "risk": True, "alternative": True, "trails": True,
        }
        self.calibration = CalibrationManager()
        self.runtime_fps = 0.0
        self.runtime_ai_fps = 0.0

    def status(self) -> Dict[str, Any]:
        return {
            "detector": self.detector.status(),
            "segmentation": self.segmenter.status(),
            "tracker": {"type": "IoU + centroid assignment + optical scale rate",
                        "distance_basis": "uncalibrated_image_plane"},
            "planner": {"type": "A* + dynamic obstacle inflation + collision-checked Chaikin smoothing",
                        "units": "uncalibrated_perspective_grid", "resolution": 0.5},
            "safety": {"type": "proximity + optical TTC + path-overlap risk",
                       "distance_basis": "uncalibrated_image_plane_proxy"},
            "calibration": self.calibration.status(),
            "frame_size": [FRAME_WIDTH, FRAME_HEIGHT],
        }

    def reset_tracking(self) -> None:
        self.tracker.reset()
        self._seg_counter = 0
        self._last_seg = None

    def set_detector_backend(self, backend: str) -> Dict[str, Any]:
        backend = str(backend)
        if backend == "ultralytics":
            self.detector = UltralyticsDetector(
                model_path=str(settings.model_dir / "yolov8n.pt"),
                conf_threshold=settings.conf_threshold,
                iou_threshold=settings.iou_threshold,
                use_cuda=settings.use_cuda)
        else:
            backend = "opencv_onnx"
            self.detector = YoloOnnxDetector(
                model_path=settings.yolo_model,
                conf_threshold=settings.conf_threshold,
                iou_threshold=settings.iou_threshold,
                use_cuda=settings.use_cuda)
        self.detector_backend = backend
        self.reset_tracking()
        return self.detector.status()

    def set_confidence(self, value: float) -> float:
        value = max(0.05, min(0.95, float(value)))
        settings.conf_threshold = value
        if hasattr(self.detector, "conf_threshold"):
            self.detector.conf_threshold = value
        return value

    def set_overlays(self, config: Dict[str, Any]) -> Dict[str, bool]:
        for key in self.overlay_config:
            if key in config:
                self.overlay_config[key] = bool(config[key])
        return dict(self.overlay_config)

    def set_runtime_stats(self, fps: float, ai_fps: float) -> None:
        self.runtime_fps = max(0.0, float(fps))
        self.runtime_ai_fps = max(0.0, float(ai_fps))

    def set_calibration(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.calibration.save(data)
        self.reset_tracking()
        return self.calibration.status()

    def clear_calibration(self) -> Dict[str, Any]:
        self.calibration.clear()
        self.reset_tracking()
        return self.calibration.status()

    def _detections_to_obstacles(self, tracks: Sequence[Track], seg: RoadSegmentation,
                                 height: int, width: int) -> List[Obstacle]:
        g = self.planner.grid
        horizon = clamp(seg.horizon_y, 0.25, 0.75)
        out: List[Obstacle] = []
        for tr in tracks:
            if tr.label not in OBSTACLE_CLASSES:
                continue
            x1, y1, x2, y2 = tr.bbox
            cx, bottom = (x1 + x2) / 2.0 / max(1, width), y2 / max(1, height)
            box_w = (x2 - x1) / max(1, width)
            # Perspective proxy: bottom of box maps near the ego, horizon maps far.
            y = 1.5 + clamp((1.0 - bottom) / max(0.05, 1.0 - horizon), 0.0, 1.0) * (g.y_max - 2.0)
            x = (cx * 2.0 - 1.0) * (g.x_max * 0.82)
            radius = clamp(box_w * 8.0, 0.35, 2.4)
            vx = clamp(tr.velocity[0] / max(1, width) * 8.0, -3.0, 3.0)
            vy = clamp(-tr.velocity[1] / max(1, height) * 20.0, -4.0, 4.0)
            out.append(Obstacle(
                id=f"track-{tr.id}", x=float(x), y=float(y), radius=float(radius),
                vx=float(vx), vy=float(vy), kind=tr.label,
                confidence=tr.confidence, source="real_camera_yolo_track",
                distance_basis="uncalibrated_monocular_image_plane_proxy"))
        return out

    def _project(self, x: float, y: float, horizon: float,
                 width: int, height: int) -> Tuple[int, int]:
        g = self.planner.grid
        u = clamp((x - g.x_min) / (g.x_max - g.x_min), 0.0, 1.0)
        v = 1.0 - clamp(y / g.y_max, 0.0, 1.0) * (1.0 - horizon)
        return int(round(u * (width - 1))), int(round(v * (height - 1)))

    def _draw_hud(self, frame: np.ndarray, detector: DetectorResult, seg: RoadSegmentation,
                  safety, plan, source_type: str, processing_ms: float) -> None:
        h, w = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 54), (12, 18, 28), -1)
        cv2.rectangle(overlay, (0, h - 28), (w, h), (12, 18, 28), -1)
        cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)
        level_colors = {"SAFE": (60, 220, 120), "CAUTION": (0, 220, 255),
                        "HIGH RISK": (0, 120, 255), "EMERGENCY STOP": (0, 0, 255)}
        color = level_colors.get(safety.level, (220, 220, 220))
        cv2.putText(frame, f"SIH-26037 | {safety.level}", (10, 19),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
        cv2.putText(frame,
                    f"YOLO {len(detector.detections)} objs | {seg.source} | A* {plan.status} | FPS {self.runtime_fps:.1f} | AI {self.runtime_ai_fps:.1f} | {processing_ms:.0f} ms",
                    (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (215, 230, 245), 1, cv2.LINE_AA)
        calibrated = self.calibration.calibration is not None
        note = ("SIM METRIC" if source_type == "simulation" else
                ("CALIBRATED flat-ground estimates | image-plane planning proxy" if calibrated else
                 "UNITS: image-plane proxy / uncalibrated; no physical distance claim"))
        if source_type == "synthetic":
            note = "SYNTHETIC TEST FRAME - NOT A REAL CAMERA | " + note
        cv2.putText(frame, note, (10, h - 9), cv2.FONT_HERSHEY_SIMPLEX,
                    0.40, (190, 210, 230), 1, cv2.LINE_AA)
        if not detector.available:
            cv2.putText(frame, detector.message[:90], (10, 72),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)

    def _annotate(self, frame: np.ndarray, detections: Sequence[Detection],
                  tracks: Sequence[Track], seg: RoadSegmentation, obstacles: Sequence[Obstacle],
                  plan, safety, detector: DetectorResult, source_type: str,
                  processing_ms: float) -> np.ndarray:
        h, w = frame.shape[:2]
        out = frame.copy()
        # Learned drivable area + lane marks.
        show_seg = self.overlay_config.get("segmentation", True)
        if show_seg and seg.drivable_mask.shape == (h, w):
            road_overlay = out.copy()
            road_overlay[seg.drivable_mask > 0] = (30, 145, 65)
            cv2.addWeighted(road_overlay, 0.28, out, 0.72, 0, out)
            lane_pts = np.argwhere(seg.lane_mask > 0)
            if len(lane_pts):
                sample = lane_pts[::max(1, len(lane_pts) // 900)]
                for y, x in sample:
                    cv2.circle(out, (int(x), int(y)), 1, (255, 220, 0), -1)
        # Alternative / predicted trajectory in cyan.
        if self.overlay_config.get("alternative", True) and plan.alternative_path:
            pts = np.array([self._project(x, y, seg.horizon_y, w, h)
                            for x, y in plan.alternative_path], dtype=np.int32)
            if len(pts) > 1:
                cv2.polylines(out, [pts], False, (255, 220, 0), 2, cv2.LINE_AA)
        # Main planned path: green safe, yellow caution, red dangerous.
        if self.overlay_config.get("path", True) and plan.path:
            pts = [self._project(x, y, seg.horizon_y, w, h) for x, y in plan.path]
            for i in range(1, len(pts)):
                cost = plan.path_costs[i] if i < len(plan.path_costs) else 0.0
                color = (40, 220, 90) if cost < 0.35 else (0, 220, 255) if cost < 0.7 else (0, 0, 255)
                cv2.line(out, pts[i - 1], pts[i], color, 3, cv2.LINE_AA)
            wp = self._project(*plan.waypoint, seg.horizon_y, w, h) if plan.waypoint else pts[0]
            cv2.circle(out, wp, 6, (0, 255, 255), 2, cv2.LINE_AA)
        goal = self._project(plan.goal[0], plan.goal[1], seg.horizon_y, w, h)
        cv2.drawMarker(out, goal, (255, 255, 255), cv2.MARKER_DIAMOND, 12, 2)
        # Predicted obstacle motion in cyan.
        for obs in obstacles:
            p0 = self._project(obs.x, obs.y, seg.horizon_y, w, h)
            p1 = self._project(obs.x + obs.vx * 1.0, obs.y + obs.vy * 1.0, seg.horizon_y, w, h)
            cv2.arrowedLine(out, p0, p1, (255, 220, 0), 1, cv2.LINE_AA, tipLength=0.3)
        # Risk zones.
        if self.overlay_config.get("risk", True):
            for zone in safety.risk_zones:
                c = self._project(zone["x"], zone["y"], seg.horizon_y, w, h)
                r = max(5, int(zone["radius"] * 7))
                ccolor = (0, 0, 255) if zone["level"] == "EMERGENCY STOP" else (
                    (0, 120, 255) if zone["level"] == "HIGH RISK" else (0, 220, 255))
                cv2.circle(out, c, r, ccolor, 1, cv2.LINE_AA)
        # Object motion trails from the tracker's measured centroid history.
        if self.overlay_config.get("trails", True):
            for tr in tracks:
                if len(tr.history) > 1:
                    pts = np.array([[int(x), int(y)] for x, y in tr.history[-15:]], dtype=np.int32)
                    cv2.polylines(out, [pts], False, (180, 120, 255), 1, cv2.LINE_AA)
        risk_by_track = {str(z.get("id")): str(z.get("level")) for z in safety.risk_zones}
        # Real YOLO boxes (never synthesized).
        if self.overlay_config.get("detections", True):
            track_by_bbox = {f"{t.bbox}": t.id for t in tracks}
            for det in detections:
                x1, y1, x2, y2 = det.bbox
                if det.label in VULNERABLE_CLASSES:
                    color = (0, 215, 255)
                elif det.label in VEHICLE_CLASSES:
                    color = (40, 90, 240)
                elif det.label in TRAFFIC_CONTROL_CLASSES:
                    color = (255, 220, 0)
                else:
                    color = (190, 120, 255)
                risk_level = risk_by_track.get(f"track-{det.track_id}") if det.track_id else None
                if risk_level == "EMERGENCY STOP":
                    color = (0, 0, 255)
                elif risk_level == "HIGH RISK":
                    color = (0, 110, 255)
                elif risk_level == "CAUTION":
                    color = (0, 220, 255)
                cv2.rectangle(out, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
                label = f"{det.label} {det.confidence:.2f}"
                if det.track_id:
                    label = f"#{det.track_id} {label}"
                elif f"{det.bbox}" in track_by_bbox:
                    label = f"#{track_by_bbox[f'{det.bbox}']} {label}"
                tw = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)[0][0]
                cv2.rectangle(out, (x1, max(0, y1 - 17)), (min(w, x1 + tw + 8), y1), color, -1)
                cv2.putText(out, label, (x1 + 3, max(12, y1 - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, (10, 15, 22), 1, cv2.LINE_AA)
        self._draw_hud(out, detector, seg, safety, plan, source_type, processing_ms)
        return out

    def process_frame(self, frame: np.ndarray, source_type: str = "camera",
                      timestamp: Optional[float] = None) -> PipelineResult:
        t0 = time.perf_counter()
        if frame is None or frame.size == 0:
            return PipelineResult(data=self.empty_result("Empty frame"), annotated=self.placeholder("EMPTY FRAME"))
        try:
            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)
            h, w = frame.shape[:2]
            t_det = time.perf_counter()
            detection = self.detector.detect(frame)
            det_ms = (time.perf_counter() - t_det) * 1000.0
            t_seg = time.perf_counter()
            run_segmentation = (self._last_seg is None or
                                self._seg_counter % self.segmentation_interval == 0)
            if run_segmentation:
                seg = self.segmenter.segment(frame)
                self._last_seg = seg
            else:
                seg = self._last_seg  # type: ignore[assignment]
            seg_cached = not run_segmentation
            seg_ms = (time.perf_counter() - t_seg) * 1000.0
            self._seg_counter += 1
            t_track = time.perf_counter()
            tracks = self.tracker.update(detection.detections, timestamp)
            track_ms = (time.perf_counter() - t_track) * 1000.0
            # Optional calibrated physical estimates; None when uncalibrated.
            for det in detection.detections:
                det.calibrated_distance = self.calibration.estimate(det.bbox, w, h)
            track_dicts = []
            for tr in tracks:
                item = tr.to_dict()
                item["calibrated_distance"] = self.calibration.estimate(tr.bbox, w, h)
                track_dicts.append(item)
            obstacles = self._detections_to_obstacles(tracks, seg, h, w)
            t_plan = time.perf_counter()
            plan = self.planner.plan(
                obstacles=obstacles,
                goal=(0.0, self.planner.grid.y_max - 1.0),
                start=(0.0, 0.0),
                drivable_polygon=seg.free_space_polygon,
                units="uncalibrated_monocular_image_plane_proxy",
                replan_reason="camera_frame",
                include_alternative=True,
            )
            plan_ms = (time.perf_counter() - t_plan) * 1000.0
            t_safe = time.perf_counter()
            safety = self.safety.assess(
                obstacles=obstacles,
                ego=(0.0, 0.0), heading=0.0, speed=1.0, max_speed=1.0,
                path=plan.path, units=plan.units, tracks=tracks,
                free_space_ratio=seg.free_space_ratio,
                planner_blocked=plan.status == "blocked",
            )
            safety_ms = (time.perf_counter() - t_safe) * 1000.0
            processing_ms = (time.perf_counter() - t0) * 1000.0
            annotated = self._annotate(frame, detection.detections, tracks, seg,
                                       obstacles, plan, safety, detection,
                                       source_type, processing_ms)
            data: Dict[str, Any] = {
                "timestamp": now_iso(),
                "source_type": source_type,
                "resolution": [w, h],
                "detection": detection.to_dict(),
                "tracks": track_dicts,
                "calibration": self.calibration.status(),
                "segmentation": {**seg.to_dict(), "cached": seg_cached},
                "segmentation_cached": seg_cached,
                "obstacles": [o.to_dict() for o in obstacles],
                "plan": plan.to_dict(),
                "safety": safety.to_dict(),
                "timings_ms": {
                    "detector": round(det_ms, 2),
                    "segmentation": round(seg_ms, 2),
                    "tracking": round(track_ms, 2),
                    "planning": round(plan_ms, 2),
                    "safety": round(safety_ms, 2),
                    "total": round(processing_ms, 2),
                },
                "model_status": self.status(),
                "distance_disclaimer": (
                    "Calibrated flat-ground inverse-perspective estimates are attached to detections, but planning still uses image-plane proxy coordinates; estimates are not ground-truth range."
                    if self.calibration.calibration else
                    "Camera distances are uncalibrated image-plane/perspective proxies. Physical distance accuracy is not claimed."),
                "notes": [
                    "Detections come from the loaded pretrained YOLOv8n ONNX model; no detections are fabricated.",
                    "Drivable area comes from the loaded pretrained TwinLiteNet ONNX model unless source says heuristic_fallback.",
                    "Planner and safety modules are shared with the simulation engine.",
                    "Motion trails, FPS, AI FPS and total processing latency are measured/annotated on each processed frame.",
                ],
            }
            if source_type == "synthetic":
                data["notes"].append("SYNTHETIC test frame: not a real camera and not a real road scene.")
            self.last_result = data
            self.last_annotated = annotated
            return PipelineResult(data=data, annotated=annotated)
        except Exception as exc:
            data = self.empty_result(f"Pipeline error: {exc}")
            data["notes"].append("The error is reported instead of substituting invented detections.")
            return PipelineResult(data=data, annotated=self.placeholder(f"PIPELINE ERROR: {str(exc)[:60]}"))

    def empty_result(self, message: str = "No active camera") -> Dict[str, Any]:
        return {
            "timestamp": now_iso(),
            "source_type": "none",
            "resolution": [0, 0],
            "detection": DetectorResult(message=message).to_dict(),
            "tracks": [], "segmentation": {"source": "none", "available": False,
                                            "free_space_ratio": 0, "message": message},
            "obstacles": [],
            "plan": {"status": "idle", "path": [], "alternative_path": [],
                     "units": "uncalibrated_monocular_image_plane_proxy", "latency_ms": 0},
            "safety": self.safety.assess([], units="uncalibrated_monocular_image_plane_proxy").to_dict(),
            "timings_ms": {}, "model_status": self.status(),
            "calibration": self.calibration.status(),
            "distance_disclaimer": "No camera frame processed.",
            "notes": [message],
        }

    @staticmethod
    def placeholder(text: str = "NO CAMERA SIGNAL") -> np.ndarray:
        img = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        img[:] = (18, 24, 34)
        for x in range(0, FRAME_WIDTH, 40):
            cv2.line(img, (x, 0), (x, FRAME_HEIGHT), (28, 38, 52), 1)
        for y in range(0, FRAME_HEIGHT, 40):
            cv2.line(img, (0, y), (FRAME_WIDTH, y), (28, 38, 52), 1)
        cv2.putText(img, text, (36, FRAME_HEIGHT // 2 - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (80, 180, 240), 2, cv2.LINE_AA)
        cv2.putText(img, "Connect phone / webcam / IP stream / video upload",
                    (36, FRAME_HEIGHT // 2 + 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.52, (170, 190, 210), 1, cv2.LINE_AA)
        return img
