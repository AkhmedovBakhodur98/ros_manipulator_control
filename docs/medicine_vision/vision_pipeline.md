# Medicine Vision Pipeline

## Overview

The `medicine_vision` project provides a standalone ML pipeline for automated medicine identification. The system uses YOLO to detect medicine boxes, medicine name regions, and code/barcode regions, then reads text via PaddleOCR, matches against a database, and verifies identity by image comparison.

**Current stage:** Offline ML training and testing — no camera, no ROS2 integration yet. All components can be tested independently with static images.

**Goal:** Validate each pipeline step on static images, then integrate with OAK-D Pro camera and ROS2 in a later phase.

---

## Project Location

```
manipulator_ros_control/
├── src/                    # ROS2 packages
├── firmware/               # Teensy firmware
└── medicine_vision/        # ← This project (standalone ML pipeline)
```

---

## Pipeline Architecture

```
  Input image (photo of medicine box)
          │
          ▼
┌──────────────────────────┐
│   Step 1: YOLO           │  train.py / predict.py
│   Detect:                │
│   - medicine_box         │  (box region)
│   - medicine name region │  (e.g., analgin, mexidol)
│   - code region          │  (e.g., analgin_code)
└────────┬─────────────────┘
         │ bounding boxes + crops
         ▼
┌──────────────────┐
│   Step 2: OCR    │  ocr_test.py
│   PaddleOCR      │
│   Read text from │
│   name/box crop  │
└────────┬─────────┘
         │ recognized text
         ▼
┌──────────────────┐
│   Step 3: DB     │  db_manager.py
│   Lookup         │
│   Match medicine │
└────────┬─────────┘
         │ candidates +
         │ reference image
         ▼
┌──────────────────┐
│   Step 4: Image  │  verify_test.py
│   Verification   │
│   SSIM / pHash   │
└────────┬─────────┘
         │
         ▼
   Medicine identified
   (medicine_id + name)
```

**Full pipeline test:** `pipeline_test.py` runs all 4 steps end-to-end.

**Note:** YOLO provides two identification signals:
1. **Class label** — the detected name region class (e.g., `analgin`) directly identifies the medicine
2. **OCR text** — PaddleOCR reads the actual text for confirmation and DB matching

This dual approach increases reliability: YOLO class gives a fast ID, OCR + DB provides verification.

---

## Project Structure

```
medicine_vision/
├── train.py                          # YOLO training (YOLO11n, 1 class: medicine_box)
├── predict.py                        # YOLO inference CLI
├── ocr_test.py                       # PaddleOCR testing (standalone or with YOLO crop)
├── verify_test.py                    # Image verification testing (SSIM + pHash)
├── pipeline_test.py                  # Full pipeline: YOLO → OCR → DB → verify
├── db_manager.py                     # Medicine database management (add/list/search/remove)
├── requirements.txt                  # Python dependencies
├── .gitignore
├── weights/                          # Trained YOLO weights (best.pt)
├── scripts/
│   ├── convert_labelme_to_yolo.py    # LabelMe JSON → YOLO bbox format
│   ├── split_dataset.py              # 80/20 train/val split
│   └── verify_labels.py             # Draw bboxes on images for visual QA
├── data/
│   ├── dataset.yaml                  # YOLO dataset config (1 class: medicine_box)
│   ├── raw/                          # Original photos + LabelMe JSON annotations
│   ├── images/{train,val}/           # Split images
│   └── labels/{train,val}/           # YOLO-format labels
└── db/
    ├── medicines.db                  # SQLite database (created on first use)
    └── reference_images/             # One reference photo per medicine
```

---

## File Descriptions

### `train.py`

Trains YOLO11n model on medicine detection dataset (multi-class).

| Parameter | Value |
|-----------|-------|
| Base model | `yolo11n.pt` (pretrained on COCO) |
| Task | Detection (bounding boxes) |
| Classes | 35 (1 box + 17 medicine names + 17 code regions) |
| Image size | 1280 |
| Epochs | 150 (with early stopping, patience=20) |
| Batch size | 16 |
| Optimizer | AdamW, cosine LR schedule |
| Freeze | First 10 layers (transfer learning) |

**Training images:** 4000x2252 resolution (phone camera). `imgsz=1280` preserves enough detail for small name/code regions while keeping training practical.

After training, evaluates best weights and prints mAP50 and mAP50-95.

**Usage:**
```bash
python train.py
```

Output: `runs/medicine_det/train/weights/best.pt` → copy to `weights/best.pt`.

**Note:** If GPU runs out of memory with `batch=16` at `imgsz=1280`, reduce batch to 8.

---

### `predict.py`

Runs YOLO inference on images, directories, or video.

**Usage:**
```bash
python predict.py --source photo.jpg
python predict.py --source test_photos/
python predict.py --source photo.jpg --conf 0.3
python predict.py --source photo.jpg --weights path/to/best.pt
```

Results saved to `runs/predict/result/`.

---

### `ocr_test.py`

Tests PaddleOCR text recognition on medicine images.

**Two modes:**
1. **Standalone** — run OCR on full image
2. **With YOLO** — detect box first, crop, then run OCR on cropped region

**Usage:**
```bash
# OCR on full image
python ocr_test.py --source photo.jpg

# OCR on directory
python ocr_test.py --source data/raw/

# Crop with YOLO first, then OCR (requires trained weights)
python ocr_test.py --source photo.jpg --use-yolo

# Russian language
python ocr_test.py --source photo.jpg --lang ru

# Adjust confidence threshold
python ocr_test.py --source photo.jpg --conf 0.8
```

**How `--use-yolo` works:**
1. Loads YOLO model from `weights/best.pt`
2. Detects medicine box regions
3. Crops each region with 10% padding
4. Runs PaddleOCR on each crop
5. Filters by confidence threshold (default 0.7)

---

### `verify_test.py`

Tests image verification by comparing a detected medicine crop against reference images.

**Methods used:**
- **SSIM** (Structural Similarity Index) — compares visual structure (0.0 = different, 1.0 = identical)
- **pHash** (Perceptual Hash) — fingerprint distance (0 = identical, higher = more different)
- **Decision:** `SSIM > 0.5 AND pHash < 15` → MATCH

Both images are resized to 224x224 before comparison.

**Usage:**
```bash
# Compare two images
python verify_test.py --detected crop.jpg --reference ref.jpg

# Compare against all reference images in directory
python verify_test.py --detected crop.jpg --reference-dir db/reference_images/

# Adjust thresholds
python verify_test.py --detected crop.jpg --reference ref.jpg \
    --ssim-threshold 0.4 --phash-threshold 20
```

---

### `pipeline_test.py`

Runs the full 4-step pipeline end-to-end on static images.

**Steps executed:**
1. **YOLO** — detect medicine boxes (requires `weights/best.pt`)
2. **PaddleOCR** — read text from each detected crop
3. **DB lookup** — fuzzy match text against `db/medicines.db` (requires database)
4. **Image verification** — compare crop vs DB reference image

**Usage:**
```bash
# Single image
python pipeline_test.py --source photo.jpg

# Directory
python pipeline_test.py --source test_photos/

# Russian OCR
python pipeline_test.py --source photo.jpg --lang ru
```

**Prerequisites:**
- Trained YOLO weights in `weights/best.pt`
- Populated medicine database (`db/medicines.db`)
- Reference images in `db/reference_images/`

**Pipeline logic per detected box:**
1. If YOLO confidence < threshold → skip
2. If OCR returns empty text → skip
3. If best DB match score < 85% → report uncertain
4. If reference image exists → run SSIM + pHash verification
5. If verified → print `RESULT: medicine_id — name`

---

### `db_manager.py`

SQLite medicine database management CLI.

**Database schema:**

| Column | Type | Description |
|--------|------|-------------|
| `medicine_id` | TEXT PK | Auto-generated (e.g., `MED-00001`) |
| `name` | TEXT | Medicine name (e.g., `Аспирин Кардио`) |
| `name_normalized` | TEXT | Lowercase for fuzzy matching |
| `aliases` | TEXT | Comma-separated alternative names |
| `reference_image` | TEXT | Filename in `db/reference_images/` |
| `barcode` | TEXT | Optional barcode string |
| `description` | TEXT | Optional description |
| `created_at` | TEXT | ISO timestamp |
| `updated_at` | TEXT | ISO timestamp |

**Database location:** `db/medicines.db` (created automatically on first use).

**Usage:**
```bash
# Add medicine with reference image
python db_manager.py add --name "Аспирин Кардио" --image photo.jpg

# Add with barcode and aliases
python db_manager.py add --name "Nurofen Express" --image nurofen.jpg \
    --barcode "4602223001234" --aliases "Нурофен Экспресс"

# List all medicines
python db_manager.py list

# Fuzzy search by text (uses rapidfuzz)
python db_manager.py search --text "аспирин"

# Remove medicine (also deletes reference image)
python db_manager.py remove --id MED-00001
```

When adding with `--image`, the image is copied to `db/reference_images/MED-XXXXX.ext`.

---

### `scripts/convert_labelme_to_yolo.py`

Converts LabelMe JSON polygon annotations to YOLO detection format (bounding boxes).

**Input:** `data/raw/*.json` (LabelMe annotations with 35 class labels)
**Output:** `data/raw/*.txt` (YOLO format: `class x_center y_center width height`, normalized)

Contains a `CLASS_MAP` dict mapping all 35 labels to class IDs (0-34). Handles both polygon and rectangle shapes — extracts the bounding box from polygon vertices.

```bash
python scripts/convert_labelme_to_yolo.py
```

---

### `scripts/split_dataset.py`

Splits annotated data into train/val sets (80/20).

**Input:** `data/raw/` (image + `.txt` pairs)
**Output:** Copies to `data/images/{train,val}/` and `data/labels/{train,val}/`

Uses fixed seed (42) for reproducible splits. Cleans target directories before copying.

```bash
python scripts/split_dataset.py
```

---

### `scripts/verify_labels.py`

Draws YOLO bounding boxes on images for visual quality assurance. Color-coded by class type:
- **Green** — `medicine_box` (class 0)
- **Blue** — medicine name regions (classes 1-17)
- **Red** — code/barcode regions (classes 18-34)

Reads class names from `data/dataset.yaml`.

**Input:** `data/images/{train,val}/` + `data/labels/{train,val}/`
**Output:** `data/verify/` (annotated images with color-coded bboxes and class labels)

```bash
python scripts/verify_labels.py
```

---

## Data Pipeline

### Step-by-step workflow

```
1. Collect photos  →  data/raw/
2. Annotate        →  labelme data/raw/ --labels medicine_box
3. Convert         →  python scripts/convert_labelme_to_yolo.py
4. Split           →  python scripts/split_dataset.py
5. Verify          →  python scripts/verify_labels.py  (check data/verify/)
6. Train           →  python train.py
7. Copy weights    →  cp runs/medicine_det/train/weights/best.pt weights/
8. Test detection  →  python predict.py --source test_photo.jpg
```

### LabelMe annotation

```bash
# Install (included in requirements.txt)
pip install labelme

# Launch annotation tool
labelme data/raw/ --output data/raw/ --labels medicine_box,analgin,analgin_code,...
```

Each image is annotated with up to 3 types of bounding boxes:
- **`medicine_box`** — the entire medicine box region (present on every image)
- **Medicine name** — the name/label region (e.g., `analgin`, `mexidol`, `furosemid`)
- **Code** — barcode/QR code region (e.g., `analgin_code`, `mexidol_code`)

### YOLO dataset config (`data/dataset.yaml`)

```yaml
path: ../data
train: images/train
val: images/val

names:
  0: medicine_box
  # Medicine name regions (1-17)
  1: analgin
  2: dimedrol
  3: droperidol
  4: drotaverin_velfarm
  5: ketorolak_velfarm
  6: klofelin
  7: magniy_sulfat
  8: mexidol
  9: metoklopramid
  10: natriy_hlorid
  11: papaverin
  12: platifilin
  13: spazmaten
  14: furosemid
  15: elzepam
  16: enap_r
  17: etamzilat
  # Code/barcode regions (18-34)
  18: analgin_code
  19: dimedrol_code
  ... (one _code class per medicine)
  34: etamzilat_code
```

### Current dataset stats

| Metric | Value |
|--------|-------|
| Total images | 314 |
| Train | 251 (80%) |
| Val | 63 (20%) |
| Classes | 35 |
| Image resolution | 4000x2252 (phone camera) |
| Medicines | 17 types |
| Source | `~/Downloads/ДатасетЯробот/` (per-medicine subdirectories + `дб/` reference photos) |

---

## Training Configuration

| Parameter | Value | Description |
|-----------|-------|-------------|
| Model | YOLO11n (`yolo11n.pt`) | Pretrained on COCO |
| Task | Detection | Bounding boxes (multi-class) |
| Classes | 35 | 1 box + 17 names + 17 codes |
| Image size | 1280 | High-res for small label regions |
| Batch size | 16 | Reduce to 8 if OOM |
| Max epochs | 150 | Early stopping with patience=20 |
| Freeze | 10 layers | Backbone frozen (transfer learning) |
| Optimizer | AdamW | With cosine LR schedule |
| LR | 0.01 → 0.0001 | Cosine annealing |

### Augmentations (configured in `train.py`)

| Augmentation | Value |
|-------------|-------|
| HSV hue | 0.015 |
| HSV saturation | 0.7 |
| HSV value | 0.4 |
| Rotation | ±15° |
| Translate | 0.1 |
| Scale | 0.5 |
| Horizontal flip | 50% |
| Mosaic | 1.0 |
| Mixup | 0.1 |
| Random erasing | 0.1 |

### Transfer learning

Backbone (first 10 layers) is frozen — only the detection head trains. This prevents overfitting on small datasets while leveraging features learned on COCO.

---

## Dependencies

### Python (`requirements.txt`)

| Package | Purpose |
|---------|---------|
| `ultralytics>=8.3.0` | YOLO11 training and inference |
| `labelme>=5.5.0` | Image annotation tool |
| `paddlepaddle>=2.6.0` | PaddleOCR backend engine |
| `paddleocr>=2.9.0` | OCR text detection and recognition |
| `rapidfuzz>=3.0.0` | Fuzzy string matching for DB lookup |
| `scikit-image>=0.22.0` | SSIM computation |
| `imagehash>=4.3.0` | Perceptual hashing |
| `opencv-python-headless>=4.9.0` | Image processing (headless to avoid Qt conflicts with LabelMe) |
| `Pillow>=10.0.0` | Image handling for pHash |

**Note:** `sqlite3` is built into Python — no install needed.

### Setup

```bash
cd medicine_vision
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Performance Targets

| Metric | Target |
|--------|--------|
| YOLO detection (mAP50) | > 0.90 |
| OCR text reading accuracy | > 90% |
| DB fuzzy matching | > 95% correct identification |
| Image verification false accept | < 1% |
| Full pipeline latency | < 200ms per image |

---

## Development Roadmap

### Phase 1: YOLO Training & Detection (current)

**Goal:** YOLO detects medicine boxes, name regions, and code regions in static images.

- [x] Collect training images (314 photos of 17 medicine types from `~/Downloads/ДатасетЯробот/`)
- [x] Annotate with LabelMe (35 classes: medicine_box + 17 names + 17 codes)
- [x] Convert annotations: `python scripts/convert_labelme_to_yolo.py` (314/314 converted)
- [x] Split dataset: `python scripts/split_dataset.py` (251 train / 63 val)
- [x] Verify labels: `python scripts/verify_labels.py` (314/314 verified)
- [ ] Train model: `python train.py`
- [ ] Evaluate (target mAP50 > 0.9)
- [ ] Test inference: `python predict.py --source test_photo.jpg`
- [ ] Copy best weights to `weights/best.pt`

**Deliverable:** `weights/best.pt` — trained YOLO model (35 classes).

---

### Phase 2: OCR Testing

**Goal:** PaddleOCR reads medicine names from detected box crops.

- [ ] Test OCR on full medicine images: `python ocr_test.py --source photo.jpg`
- [ ] Test OCR with YOLO crop: `python ocr_test.py --source photo.jpg --use-yolo`
- [ ] Test with Russian text: `python ocr_test.py --source photo.jpg --lang ru`
- [ ] Benchmark accuracy on 50+ medicine types
- [ ] Tune confidence threshold if needed

**Deliverable:** OCR correctly reads medicine names with >90% accuracy.

---

### Phase 3: Database & Matching

**Goal:** Match recognized text to medicine database.

- [ ] Populate database: `python db_manager.py add --name "..." --image photo.jpg`
- [ ] Test fuzzy search: `python db_manager.py search --text "..."`
- [ ] Verify matching accuracy across medicine catalog
- [ ] Tune fuzzy match threshold (default 85%)

**Deliverable:** Text → medicine_id matching with >95% accuracy.

---

### Phase 4: Image Verification

**Goal:** Confirm medicine identity by comparing images.

- [ ] Capture reference images for all medicines in DB
- [ ] Test verification: `python verify_test.py --detected crop.jpg --reference ref.jpg`
- [ ] Tune thresholds (SSIM, pHash distance)
- [ ] Measure false accept / false reject rates
- [ ] (Fallback) If SSIM/pHash insufficient, consider CLIP embeddings

**Deliverable:** Verification reduces false identification to <1%.

---

### Phase 5: Full Pipeline Validation

**Goal:** All 4 steps work together end-to-end.

- [ ] Run full pipeline: `python pipeline_test.py --source test_photos/`
- [ ] Test on varied conditions (angles, lighting, partial occlusion)
- [ ] Measure end-to-end accuracy and latency
- [ ] Fix any integration issues between steps

**Deliverable:** Pipeline correctly identifies medicines in >90% of test cases.

---

### Phase 6: Camera Bring-Up (requires OAK-D Pro hardware)

**Goal:** OAK-D Pro running in ROS2, publishing RGB + depth.

- [ ] Install `depthai-ros` for ROS2 Jazzy
- [ ] Launch OAK-D Pro, verify RGB and depth topics
- [ ] Verify depth alignment (RGB-depth overlay in RViz)
- [ ] Determine camera mounting position on the robot
- [ ] Create static TF for camera mount (or add to URDF)
- [ ] Validate depth accuracy at working distance (~30-50cm)

**Deliverable:** Camera publishes RGB + aligned depth, visible in RViz.

---

### Phase 7: ROS2 Node Integration

**Goal:** Vision pipeline as a ROS2 node with 3D localization.

- [ ] Create `src/medicine_vision/` ROS2 package
- [ ] Implement vision node (wraps pipeline from this project)
- [ ] Add 3D localization: pixel + depth → robot coordinates via TF
- [ ] Define custom messages (`MedicineDetection.msg`) and services (`DetectMedicine.srv`)
- [ ] Create launch files (vision node + OAK-D Pro driver)
- [ ] Integrate with `PickItemsFromWarehouse` action server
- [ ] End-to-end test: detect → identify → locate → pick

**Deliverable:** Working vision node integrated with the robot system.

---

### Phase 8: Production Hardening

**Goal:** Reliable operation, easy medicine onboarding.

- [ ] Handle multiple medicines in single frame
- [ ] Add retry logic (re-capture if detection/OCR fails)
- [ ] Logging and diagnostics (detection time, confidence stats)
- [ ] Performance optimization (target: <200ms full pipeline)
- [ ] Medicine onboarding guide

**Deliverable:** Production-ready vision system.

---

## Future: ROS2 Integration Design

When the offline pipeline is validated (Phase 5 complete), the system will be integrated into ROS2 as a `src/medicine_vision/` package. Planned ROS2 interfaces:

### Subscribed Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/oak/rgb/image_raw` | `sensor_msgs/Image` | Color image from OAK-D Pro |
| `/oak/stereo/depth` | `sensor_msgs/Image` | Aligned depth map (16UC1, mm) |
| `/oak/rgb/camera_info` | `sensor_msgs/CameraInfo` | Camera intrinsics |

### Published Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/medicine_vision/detections` | `medicine_vision/msg/MedicineDetection` | Detected + verified medicines with 3D poses |
| `/medicine_vision/debug_image` | `sensor_msgs/Image` | Annotated image for visualization |

### Services

| Service | Type | Description |
|---------|------|-------------|
| `/medicine_vision/detect` | `medicine_vision/srv/DetectMedicine` | On-demand single detection |

### 3D Localization (Phase 7)

The OAK-D Pro provides aligned depth maps. Given a YOLO bounding box center `(px, py)`:

```python
# Sample depth at box center (median of small region for robustness)
z_mm = np.median(depth_frame[py-5:py+5, px-5:px+5])
z = z_mm / 1000.0  # mm → meters

# Back-project to 3D using camera intrinsics
X = (px - cx) * z / fx
Y = (py - cy) * z / fy
Z = z

# Transform from camera frame to robot frame via TF
```

### Integration with Existing System

```
Current flow:
  WMS (REST API) → get_items request → PickItemsFromWarehouse
                    (medicine_list with image_id, box position)

Future flow with vision:
  WMS (REST API) → get_items request → PickItemsFromWarehouse
                                              │
                                              ▼
                                     Call /medicine_vision/detect
                                              │
                                              ▼
                                     Vision returns:
                                       - medicine_id (verified)
                                       - (X, Y, Z) grasp point
                                              │
                                              ▼
                                     Arm moves to (X, Y, Z)
                                     and picks the medicine
```

---

## Hardware (for future phases)

### OAK-D Pro Stereo Camera

| Spec | Value |
|------|-------|
| RGB sensor | IMX378 (12MP, 4056x3040) |
| Stereo pair | 2x OV9282 (1MP, 1280x800) |
| Depth technology | Active stereo (IR dot projector + IR illumination LED) |
| Depth range | ~20cm to 35m |
| On-device NN | Intel Myriad X VPU (~4 TOPS) |
| Interface | USB-C |
| ROS2 driver | `depthai-ros` |

**Why OAK-D Pro:**
- IR dot projector enables accurate depth on flat/textureless surfaces (medicine boxes)
- IR illumination for consistent performance in varying light
- On-device YOLO inference possible (reduces host CPU load)
- Native ROS2 support with depth-aligned RGB

---

## Related Documentation

- **AR4 Hardware Interface:** `../ar4_hardware_interface/package_structure.md`
- **AR4 Description:** `../ar4_description/package_structure.md`
- **SCARA Control:** `../scara_control/package_structure.md`
- **PickItems Server:** `../ros_control/pick_items_from_warehouse_server.md`
- **REST API Bridge:** `../rest_api_bridge/package_structure.md`
- **OAK-D Pro Hardware:** https://docs.luxonis.com/projects/hardware/en/latest/pages/DM9098pro.html
- **depthai-ros:** https://github.com/luxonis/depthai-ros
