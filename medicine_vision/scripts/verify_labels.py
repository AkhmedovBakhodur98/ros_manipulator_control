"""Visualize YOLO detection labels overlaid on images for QA."""

from pathlib import Path

import cv2
import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VERIFY_DIR = DATA_DIR / "verify"
THICKNESS = 2

# Colors per class type
COLOR_BOX = (0, 255, 0)    # Green — medicine_box
COLOR_NAME = (255, 128, 0)  # Blue — medicine name regions
COLOR_CODE = (0, 0, 255)    # Red — code/barcode regions

# Load class names from dataset.yaml
import yaml
with open(DATA_DIR / "dataset.yaml") as f:
    _cfg = yaml.safe_load(f)
CLASS_NAMES = _cfg["names"]


def get_color(class_id):
    if class_id == 0:
        return COLOR_BOX
    elif class_id <= 17:
        return COLOR_NAME
    else:
        return COLOR_CODE


def draw_label(img_path: Path, txt_path: Path, out_path: Path):
    """Draw bounding boxes on image and save."""
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"  Cannot read {img_path.name}")
        return False

    h, w = img.shape[:2]

    with open(txt_path) as f:
        lines = f.read().strip().splitlines()

    for line in lines:
        parts = line.split()
        class_id = int(parts[0])
        x_center = float(parts[1]) * w
        y_center = float(parts[2]) * h
        box_w = float(parts[3]) * w
        box_h = float(parts[4]) * h

        x1 = int(x_center - box_w / 2)
        y1 = int(y_center - box_h / 2)
        x2 = int(x_center + box_w / 2)
        y2 = int(y_center + box_h / 2)

        color = get_color(class_id)
        label_name = CLASS_NAMES.get(class_id, str(class_id))
        cv2.rectangle(img, (x1, y1), (x2, y2), color, THICKNESS)
        cv2.putText(img, label_name, (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, THICKNESS)

    cv2.putText(img, f"{len(lines)} annotation(s)", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR_BOX, 2)

    cv2.imwrite(str(out_path), img)
    return True


def main():
    VERIFY_DIR.mkdir(exist_ok=True)

    total = 0
    verified = 0

    for split in ["train", "val"]:
        img_dir = DATA_DIR / "images" / split
        lbl_dir = DATA_DIR / "labels" / split

        for txt_path in sorted(lbl_dir.glob("*.txt")):
            # Find matching image
            img_path = None
            for ext in [".jpg", ".jpeg", ".png"]:
                candidate = img_dir / (txt_path.stem + ext)
                if candidate.exists():
                    img_path = candidate
                    break

            if img_path is None:
                print(f"  No image for {txt_path.name}")
                continue

            total += 1
            out_name = f"{split}_{img_path.name}"
            if draw_label(img_path, txt_path, VERIFY_DIR / out_name):
                verified += 1

    print(f"Verified {verified}/{total} images -> data/verify/")


if __name__ == "__main__":
    main()
