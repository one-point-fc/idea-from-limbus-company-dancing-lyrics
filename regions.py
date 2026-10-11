"""Six editable screen rectangles, stored as portable screen percentages."""
import json
import math

REGION_NAMES = {
    "top_left": "左上", "top_right": "右上",
    "middle_left": "左中", "middle_right": "右中",
    "bottom_left": "左下", "bottom_right": "右下",
}
DEFAULT_BOXES = {key: [2 if key.endswith("left") else 68,
                      {"top": 2, "middle": 37, "bottom": 72}[key.split("_")[0]], 30, 26]
                 for key in REGION_NAMES}
DEFAULT_BOXES_JSON = json.dumps(DEFAULT_BOXES)
DEFAULT_SELECTION = "top_left,top_right"


def selected_regions(value):
    selected = set(str(value).split(","))
    return [key for key in REGION_NAMES if key in selected] or DEFAULT_SELECTION.split(",")


def region_boxes(value):
    try:
        raw = json.loads(value)
    except (ValueError, TypeError):
        raw = {}
    result = {}
    for key, default in DEFAULT_BOXES.items():
        box = raw.get(key) if isinstance(raw, dict) else None
        if (not isinstance(box, list) or len(box) != 4
                or any(type(n) not in (int, float) or not math.isfinite(n) for n in box)):
            box = default
        x, y = [max(0, min(95, n)) for n in box[:2]]
        w, h = max(5, min(100-x, box[2])), max(5, min(100-y, box[3]))
        result[key] = [round(n, 2) for n in (x, y, w, h)]
    return result
