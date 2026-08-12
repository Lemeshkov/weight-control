# Offline dataset: `weighbridge_vehicle`

This research pipeline does not import or modify production camera, FSM, LiDAR, API, database, or frontend code. Images, labels, runs, weights, and reports live under ignored `diagnostics/training/`.

## Annotation policy

Use exactly one class: `0 = weighbridge_vehicle`. Draw one tight rectangle around the actually visible part of the vehicle. Cab and body of the same vehicle are one object. Do not extend a box outside the image, infer an invisible part, include a large cast shadow, or label fixed weighbridge structures. An image with no vehicle has an empty `.txt` label. Partial entry/exit remains a positive image with a box around only the visible pixels.

The preparation script writes empty labels only when full `VEHICLE_ENTERED`/`VEHICLE_EXITED` markers prove that the frame is outside the active interval. Positive and legacy-session images stay without labels until human review. A missing pretrained COCO detection never means “no vehicle”.

## Prepare and annotate

From `backend/`:

```powershell
..\venv_weight\Scripts\python.exe scripts\prepare_weighbridge_vehicle_dataset.py --clean
..\venv_weight\Scripts\python.exe scripts\validate_weighbridge_vehicle_dataset.py ..\diagnostics\training\weighbridge_vehicle\dataset --allow-incomplete
```

Recommended Windows annotation tool: [CVAT Community](https://docs.cvat.ai/docs/administration/basics/installation/), because it supports rectangle hotkeys, review, and [Ultralytics YOLO export](https://docs.cvat.ai/docs/dataset_management/formats/format-yolo-ultralytics/). Install Docker Desktop and WSL2, clone CVAT in a separate tools directory, run `docker compose up -d`, then create the first account with `docker exec -it cvat_server bash -ic 'python3 ~/manage.py createsuperuser'` and open `http://localhost:8080` in Chrome. Create label `weighbridge_vehicle`, upload one split at a time, annotate/review every frame, and export `Ultralytics YOLO Detection 1.0`. Copy each exported split's `.txt` files into the matching `labels/train`, `labels/val`, or `labels/test` directory. Preserve the image names and do not randomize splits in CVAT. Update `annotation_status` in `dataset_manifest.csv` to `COMPLETE` after review.

The current split is by complete session/pass: TRAIN (`c178…`, `82c…`, `9fafd…`), DEV/val (`c65…`), and internal TEST (`0700…`). All were previously inspected, so TEST is not independent. Never move neighboring frames independently between splits. The next detector-frozen physical passes must be recorded as `UNSEEN_VALIDATION` and kept outside training.

## Validate, train, evaluate

Strict validation (training refuses incomplete or invalid data):

```powershell
..\venv_weight\Scripts\python.exe scripts\validate_weighbridge_vehicle_dataset.py ..\diagnostics\training\weighbridge_vehicle\dataset
```

CVAT can round a box exactly on an image edge a few decimal places outside the normalized boundary. Inspect first, then dry-run and apply the guarded normalizer. It clips only overflow up to `1e-5` and rejects larger geometry errors:

```powershell
..\venv_weight\Scripts\python.exe scripts\normalize_weighbridge_vehicle_labels.py ..\diagnostics\training\weighbridge_vehicle\dataset\labels\train
..\venv_weight\Scripts\python.exe scripts\normalize_weighbridge_vehicle_labels.py ..\diagnostics\training\weighbridge_vehicle\dataset\labels\train --apply
```

CPU baseline:

```powershell
..\venv_weight\Scripts\python.exe scripts\train_weighbridge_vehicle_detector.py ..\diagnostics\training\weighbridge_vehicle\dataset\data.yaml --model yolo11n.pt --epochs 60 --imgsz 640 --device cpu
```

Use `--device 0` only when PyTorch reports CUDA available; the script refuses an unavailable CUDA request. Weights are written below `diagnostics/training/weighbridge_vehicle/runs/baseline/weights/`.

Evaluation after training:

```powershell
..\venv_weight\Scripts\python.exe scripts\evaluate_weighbridge_vehicle_detector.py ..\diagnostics\training\weighbridge_vehicle\dataset\data.yaml ..\diagnostics\training\weighbridge_vehicle\runs\baseline\weights\best.pt --split test
```

The predeclared gate for starting separate ByteTrack research is presence recall at least 90%, negative-frame false-positive rate at most 2%, longest missed active interval at most 1000 ms, plus manual review of `annotated_test/`. This prioritizes continuous observation: high mAP alone cannot compensate for long gaps. Passing internal TEST is not independent validation; unseen physical passes are still mandatory.

Required unseen passes after freezing weights: at least three ordinary stop/resume passes by different vehicles or loads, two no-stop passes, and one adverse-light/shadow pass. Each needs ENTER/STOP/RESUME/EXIT (or ENTER/EXIT for no-stop), empty-platform lead-in/tail, and the same camera configuration.
