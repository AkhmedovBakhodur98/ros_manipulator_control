"""Test full pipeline: YOLO detect → OCR read → DB match → image verify.

Usage:
    python pipeline_test.py --source photo.jpg
    python pipeline_test.py --source photos_dir/
    python pipeline_test.py --source photo.jpg --lang ru --verbose
"""

import argparse
import sqlite3
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import imagehash
from skimage.metrics import structural_similarity as ssim
from paddleocr import PaddleOCR
from ultralytics import YOLO

WEIGHTS = Path(__file__).resolve().parent / "weights" / "best.pt"
DB_PATH = Path(__file__).resolve().parent / "db" / "medicines.db"
REF_DIR = Path(__file__).resolve().parent / "db" / "reference_images"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


# --- Step 1: YOLO detection ---

def detect_boxes(model, image_path, conf=0.5):
    """Detect medicine boxes, return list of (x1, y1, x2, y2, confidence)."""
    results = model.predict(source=str(image_path), conf=conf, verbose=False)
    img = cv2.imread(str(image_path))
    h, w = img.shape[:2]

    detections = []
    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            confidence = float(box.conf[0])
            # Add padding
            pad_x = int((x2 - x1) * 0.1)
            pad_y = int((y2 - y1) * 0.1)
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(w, x2 + pad_x)
            y2 = min(h, y2 + pad_y)
            detections.append((x1, y1, x2, y2, confidence))
    return img, detections


# --- Step 2: OCR ---

def read_text(ocr, crop, conf_threshold=0.7):
    """Read text from cropped image."""
    results = ocr.ocr(crop)
    if not results or not results[0]:
        return ""

    texts = []
    for line in results[0]:
        text, confidence = line[1]
        if confidence >= conf_threshold:
            texts.append(text)
    return " ".join(texts)


# --- Step 3: DB lookup ---

def lookup_medicine(text, db_path):
    """Fuzzy match recognized text against medicine database."""
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        print("Install rapidfuzz: pip install rapidfuzz")
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT medicine_id, name, name_normalized, reference_image FROM medicines").fetchall()
    conn.close()

    if not rows:
        return []

    choices = {row["medicine_id"]: row["name_normalized"] for row in rows}
    matches = process.extract(
        text.lower().strip(), choices,
        scorer=fuzz.token_sort_ratio,
        limit=3
    )

    results = []
    for name_norm, score, med_id in matches:
        row = next(r for r in rows if r["medicine_id"] == med_id)
        results.append({
            "medicine_id": med_id,
            "name": row["name"],
            "score": score,
            "reference_image": row["reference_image"],
        })
    return results


# --- Step 4: Image verification ---

def verify_image(crop, reference_path, ssim_thresh=0.5, phash_thresh=15):
    """Compare detected crop with reference image."""
    ref = cv2.imread(str(reference_path))
    if ref is None:
        return False, 0.0, 99

    size = (224, 224)
    a = cv2.resize(crop, size)
    b = cv2.resize(ref, size)

    ssim_score = ssim(a, b, channel_axis=2)

    hash_a = imagehash.phash(Image.fromarray(cv2.cvtColor(a, cv2.COLOR_BGR2RGB)))
    hash_b = imagehash.phash(Image.fromarray(cv2.cvtColor(b, cv2.COLOR_BGR2RGB)))
    phash_dist = hash_a - hash_b

    verified = ssim_score > ssim_thresh and phash_dist < phash_thresh
    return verified, ssim_score, phash_dist


# --- Full pipeline ---

def run_pipeline(image_path, model, ocr, verbose=False):
    """Run full pipeline on a single image."""
    print(f"\n{'='*70}")
    print(f"Image: {image_path.name}")
    print(f"{'='*70}")

    # Step 1: Detect
    img, detections = detect_boxes(model, image_path)
    print(f"\n[Step 1] YOLO: {len(detections)} medicine box(es) detected")

    if not detections:
        print("  No detections — pipeline stops")
        return

    for i, (x1, y1, x2, y2, conf) in enumerate(detections):
        print(f"\n--- Box {i+1} (conf={conf:.2f}, bbox=[{x1},{y1},{x2},{y2}]) ---")

        crop = img[y1:y2, x1:x2]

        # Step 2: OCR
        text = read_text(ocr, crop)
        print(f"[Step 2] OCR: '{text}'")

        if not text:
            print("  No text recognized — skipping")
            continue

        # Step 3: DB lookup
        if not DB_PATH.exists():
            print("[Step 3] DB: database not found, skipping lookup")
            continue

        matches = lookup_medicine(text, DB_PATH)
        if not matches:
            print("[Step 3] DB: no matches found")
            continue

        print(f"[Step 3] DB matches:")
        for m in matches:
            print(f"  {m['score']:.0f}% — {m['medicine_id']} — {m['name']}")

        best = matches[0]
        if best["score"] < 85:
            print(f"  Best match {best['score']:.0f}% < 85% threshold — uncertain")
            continue

        # Step 4: Verify
        if best["reference_image"]:
            ref_path = REF_DIR / best["reference_image"]
            verified, ssim_score, phash_dist = verify_image(crop, ref_path)
            status = "VERIFIED" if verified else "REJECTED"
            print(f"[Step 4] Verify: SSIM={ssim_score:.3f}, pHash={phash_dist}, [{status}]")

            if verified:
                print(f"\n  >>> RESULT: {best['medicine_id']} — {best['name']}")
            else:
                print(f"  Verification failed — identity uncertain")
        else:
            print(f"[Step 4] Verify: no reference image in DB, skipping")
            print(f"\n  >>> RESULT (unverified): {best['medicine_id']} — {best['name']}")


def main():
    parser = argparse.ArgumentParser(description="Full medicine vision pipeline test")
    parser.add_argument("--source", required=True, help="Image or directory path")
    parser.add_argument("--lang", default="en", help="OCR language")
    parser.add_argument("--conf", type=float, default=0.5, help="YOLO confidence threshold")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Load models
    print("Loading YOLO model...")
    model = YOLO(str(WEIGHTS))

    print("Loading PaddleOCR...")
    ocr = PaddleOCR(lang=args.lang, use_angle_cls=True, show_log=False)

    source = Path(args.source)
    if source.is_dir():
        images = sorted(p for p in source.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    else:
        images = [source]

    print(f"Processing {len(images)} image(s)")

    for img_path in images:
        run_pipeline(img_path, model, ocr, verbose=args.verbose)

    print(f"\n{'='*70}")
    print(f"Done. Processed {len(images)} image(s)")


if __name__ == "__main__":
    main()
