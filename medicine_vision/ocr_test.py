"""Test PaddleOCR on medicine box images.

Usage:
    # Single image
    python ocr_test.py --source photo.jpg

    # Directory of images
    python ocr_test.py --source data/raw/

    # With YOLO crop first (requires trained weights)
    python ocr_test.py --source photo.jpg --use-yolo

    # Specify language
    python ocr_test.py --source photo.jpg --lang ru
"""

import argparse
from pathlib import Path

import cv2
from paddleocr import PaddleOCR

WEIGHTS = Path(__file__).resolve().parent / "weights/best.pt"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def read_text(ocr, image, conf_threshold=0.7):
    """Run OCR on image, return list of (text, confidence)."""
    results = ocr.ocr(image)
    if not results or not results[0]:
        return []

    texts = []
    for line in results[0]:
        text, confidence = line[1]
        if confidence >= conf_threshold:
            texts.append((text, confidence))
    return texts


def crop_with_yolo(image_path, conf=0.5):
    """Detect medicine boxes with YOLO, return cropped regions."""
    from ultralytics import YOLO

    model = YOLO(str(WEIGHTS))
    results = model.predict(source=str(image_path), conf=conf, verbose=False)

    img = cv2.imread(str(image_path))
    crops = []
    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            # Add 10% padding
            h, w = img.shape[:2]
            pad_x = int((x2 - x1) * 0.1)
            pad_y = int((y2 - y1) * 0.1)
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(w, x2 + pad_x)
            y2 = min(h, y2 + pad_y)
            crops.append(img[y1:y2, x1:x2])
    return crops


def process_image(ocr, image_path, use_yolo=False, conf_threshold=0.7):
    """Process a single image: optionally crop with YOLO, then OCR."""
    print(f"\n{'='*60}")
    print(f"Image: {image_path.name}")
    print(f"{'='*60}")

    if use_yolo:
        crops = crop_with_yolo(image_path)
        if not crops:
            print("  No medicine boxes detected by YOLO")
            return
        for i, crop in enumerate(crops):
            print(f"\n  Box {i+1}:")
            texts = read_text(ocr, crop, conf_threshold)
            if not texts:
                print("    No text recognized")
            for text, conf in texts:
                print(f"    [{conf:.2f}] {text}")
    else:
        img = cv2.imread(str(image_path))
        texts = read_text(ocr, img, conf_threshold)
        if not texts:
            print("  No text recognized")
        for text, conf in texts:
            print(f"  [{conf:.2f}] {text}")


def main():
    parser = argparse.ArgumentParser(description="Test PaddleOCR on medicine images")
    parser.add_argument("--source", required=True, help="Image or directory path")
    parser.add_argument("--lang", default="en", help="OCR language: en, ru, etc.")
    parser.add_argument("--conf", type=float, default=0.7, help="OCR confidence threshold")
    parser.add_argument("--use-yolo", action="store_true", help="Crop with YOLO before OCR")
    args = parser.parse_args()

    ocr = PaddleOCR(lang=args.lang, use_angle_cls=True, show_log=False)

    source = Path(args.source)
    if source.is_dir():
        images = sorted(p for p in source.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    else:
        images = [source]

    print(f"Processing {len(images)} image(s), lang={args.lang}")

    for img_path in images:
        process_image(ocr, img_path, use_yolo=args.use_yolo, conf_threshold=args.conf)

    print(f"\nDone. Processed {len(images)} image(s)")


if __name__ == "__main__":
    main()
