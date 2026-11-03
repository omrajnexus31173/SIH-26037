"""COCO class names used by YOLOv8n, plus obstacle grouping for the planner."""

COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
]

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "bicycle", "train"}
VULNERABLE_CLASSES = {"person", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}
TRAFFIC_CONTROL_CLASSES = {"stop sign", "traffic light"}
OBSTACLE_CLASSES = VEHICLE_CLASSES | VULNERABLE_CLASSES | {"stop sign", "traffic light", "bench", "chair"}


def class_name(class_id: int) -> str:
    if 0 <= int(class_id) < len(COCO_NAMES):
        return COCO_NAMES[int(class_id)]
    return f"class_{class_id}"
