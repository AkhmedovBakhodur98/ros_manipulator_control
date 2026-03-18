"""Train YOLOv11n on medicine box detection dataset."""

from ultralytics import YOLO

MODEL = "yolo11n.pt"
DATASET = "data/dataset.yaml"


def main():
    model = YOLO(MODEL)

    model.train(
        data=DATASET,
        epochs=150,
        imgsz=1280,
        batch=16,
        freeze=10,
        patience=20,
        optimizer="AdamW",
        lr0=0.01,
        lrf=0.01,
        cos_lr=True,
        # Augmentation
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=15,
        translate=0.1,
        scale=0.5,
        fliplr=0.5,
        flipud=0.0,
        mosaic=1.0,
        mixup=0.1,
        erasing=0.1,
        close_mosaic=10,
        # Output
        project="runs/medicine_det",
        name="train",
    )

    # Evaluate best weights
    from pathlib import Path

    best_path = sorted(Path("runs").rglob("best.pt"))[-1]
    best = YOLO(str(best_path))
    metrics = best.val(data=DATASET)
    print(f"\nmAP50:    {metrics.box.map50:.4f}")
    print(f"mAP50-95: {metrics.box.map:.4f}")


if __name__ == "__main__":
    main()
