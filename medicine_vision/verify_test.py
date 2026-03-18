"""Test image verification: compare detected medicine with DB reference image.

Usage:
    # Compare two images
    python verify_test.py --detected photo1.jpg --reference photo2.jpg

    # Compare detected image against all references in db/
    python verify_test.py --detected photo1.jpg --reference-dir db/reference_images/

    # Adjust thresholds
    python verify_test.py --detected photo1.jpg --reference photo2.jpg \
        --ssim-threshold 0.4 --phash-threshold 20
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import imagehash
from skimage.metrics import structural_similarity as ssim

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
TARGET_SIZE = (224, 224)


def compute_ssim(img1, img2):
    """Compute SSIM between two images."""
    a = cv2.resize(img1, TARGET_SIZE)
    b = cv2.resize(img2, TARGET_SIZE)
    score = ssim(a, b, channel_axis=2)
    return score


def compute_phash(img1, img2):
    """Compute perceptual hash distance between two images."""
    a = Image.fromarray(cv2.cvtColor(cv2.resize(img1, TARGET_SIZE), cv2.COLOR_BGR2RGB))
    b = Image.fromarray(cv2.cvtColor(cv2.resize(img2, TARGET_SIZE), cv2.COLOR_BGR2RGB))
    hash_a = imagehash.phash(a)
    hash_b = imagehash.phash(b)
    return hash_a - hash_b


def verify(detected, reference, ssim_thresh=0.5, phash_thresh=15):
    """Compare two images. Return (verified, ssim_score, phash_distance)."""
    ssim_score = compute_ssim(detected, reference)
    phash_dist = compute_phash(detected, reference)
    verified = ssim_score > ssim_thresh and phash_dist < phash_thresh
    return verified, ssim_score, phash_dist


def main():
    parser = argparse.ArgumentParser(description="Test image verification")
    parser.add_argument("--detected", required=True, help="Detected medicine image")
    parser.add_argument("--reference", help="Single reference image to compare")
    parser.add_argument("--reference-dir", help="Directory of reference images")
    parser.add_argument("--ssim-threshold", type=float, default=0.5)
    parser.add_argument("--phash-threshold", type=int, default=15)
    args = parser.parse_args()

    detected = cv2.imread(args.detected)
    if detected is None:
        print(f"Cannot read: {args.detected}")
        return

    if args.reference:
        references = [Path(args.reference)]
    elif args.reference_dir:
        ref_dir = Path(args.reference_dir)
        references = sorted(p for p in ref_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    else:
        print("Provide --reference or --reference-dir")
        return

    print(f"Detected image: {args.detected}")
    print(f"Thresholds: SSIM > {args.ssim_threshold}, pHash < {args.phash_threshold}")
    print(f"{'='*60}")

    for ref_path in references:
        ref = cv2.imread(str(ref_path))
        if ref is None:
            print(f"  Cannot read: {ref_path}")
            continue

        verified, ssim_score, phash_dist = verify(
            detected, ref, args.ssim_threshold, args.phash_threshold
        )

        status = "MATCH" if verified else "NO MATCH"
        print(f"  {ref_path.name:30s}  SSIM={ssim_score:.3f}  pHash={phash_dist:3d}  [{status}]")


if __name__ == "__main__":
    main()
