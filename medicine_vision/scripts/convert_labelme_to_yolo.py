"""Convert LabelMe JSON annotations to YOLO detection format (bounding boxes)."""

import json
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CLASS_MAP = {
    "medicine_box": 0,
    # Medicine name regions
    "analgin": 1,
    "dimedrol": 2,
    "droperidol": 3,
    "drotaverin_velfarm": 4,
    "ketorolak_velfarm": 5,
    "klofelin": 6,
    "magniy_sulfat": 7,
    "mexidol": 8,
    "metoklopramid": 9,
    "natriy_hlorid": 10,
    "papaverin": 11,
    "platifilin": 12,
    "spazmaten": 13,
    "furosemid": 14,
    "elzepam": 15,
    "enap_r": 16,
    "etamzilat": 17,
    # Code/barcode regions
    "analgin_code": 18,
    "dimedrol_code": 19,
    "droperidol_code": 20,
    "drotaverin_velfarm_code": 21,
    "ketorolak_velfarm_code": 22,
    "klofelin_code": 23,
    "magniy_sulfat_code": 24,
    "mexidol_code": 25,
    "metoklopramid_code": 26,
    "natriy_hlorid_code": 27,
    "papaverin_code": 28,
    "platifilin_code": 29,
    "spazmaten_code": 30,
    "furosemid_code": 31,
    "elzepam_code": 32,
    "enap_r_code": 33,
    "etamzilat_code": 34,
}


def convert_one(json_path: Path) -> str | None:
    """Convert a single LabelMe JSON to YOLO bbox line(s)."""
    with open(json_path) as f:
        data = json.load(f)

    img_w = data["imageWidth"]
    img_h = data["imageHeight"]

    lines = []
    for shape in data["shapes"]:
        label = shape["label"]
        if label not in CLASS_MAP:
            print(f"  Skipping unknown label '{label}' in {json_path.name}")
            continue

        class_id = CLASS_MAP[label]

        # Get bounding box from polygon or rectangle
        points = shape["points"]
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)

        # YOLO format: class x_center y_center width height (normalized)
        x_center = ((x_min + x_max) / 2) / img_w
        y_center = ((y_min + y_max) / 2) / img_h
        width = (x_max - x_min) / img_w
        height = (y_max - y_min) / img_h

        lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")

    return "\n".join(lines) if lines else None


def main():
    json_files = sorted(RAW_DIR.glob("*.json"))
    print(f"Found {len(json_files)} annotation files in {RAW_DIR}")

    converted = 0
    for json_path in json_files:
        result = convert_one(json_path)
        if result is None:
            print(f"  No valid shapes in {json_path.name}, skipping")
            continue

        txt_path = json_path.with_suffix(".txt")
        txt_path.write_text(result)
        converted += 1

    print(f"Converted {converted}/{len(json_files)} files")


if __name__ == "__main__":
    main()
