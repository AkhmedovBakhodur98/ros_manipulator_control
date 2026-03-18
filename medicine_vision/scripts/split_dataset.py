"""Split annotated data into train/val sets (80/20)."""

import random
import shutil
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SPLIT_RATIO = 0.8
SEED = 42
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def main():
    # Find all images that have a matching .txt label
    pairs = []
    for img_path in sorted(RAW_DIR.iterdir()):
        if img_path.suffix.lower() not in IMAGE_EXTS:
            continue
        txt_path = img_path.with_suffix(".txt")
        if txt_path.exists():
            pairs.append((img_path, txt_path))

    print(f"Found {len(pairs)} image-label pairs")

    # Shuffle and split
    random.seed(SEED)
    random.shuffle(pairs)
    split_idx = int(len(pairs) * SPLIT_RATIO)
    train_pairs = pairs[:split_idx]
    val_pairs = pairs[split_idx:]

    print(f"Train: {len(train_pairs)}, Val: {len(val_pairs)}")

    # Copy files
    for split_name, split_pairs in [("train", train_pairs), ("val", val_pairs)]:
        img_dir = DATA_DIR / "images" / split_name
        lbl_dir = DATA_DIR / "labels" / split_name

        # Clean existing files
        for f in img_dir.glob("*"):
            f.unlink()
        for f in lbl_dir.glob("*"):
            f.unlink()

        for img_path, txt_path in split_pairs:
            shutil.copy2(img_path, img_dir / img_path.name)
            shutil.copy2(txt_path, lbl_dir / txt_path.name)

    print("Done. Files copied to data/images/ and data/labels/")


if __name__ == "__main__":
    main()
