"""Guarded offline Ultralytics fine-tuning entry point (never imported by production)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.validate_weighbridge_vehicle_dataset import validate
except ModuleNotFoundError:
    from validate_weighbridge_vehicle_dataset import validate


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("data", type=Path)
    parser.add_argument("--model", default="yolo11n.pt"); parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--imgsz", type=int, default=640); parser.add_argument("--device", default="cpu")
    parser.add_argument("--output", type=Path, default=Path("../diagnostics/training/weighbridge_vehicle/runs"))
    parser.add_argument("--name", default="baseline")
    args = parser.parse_args(); root = args.data.resolve().parent
    report = validate(root)
    if not report["valid"] or not report["complete"]:
        raise SystemExit("Dataset validation failed or manual annotation is incomplete; training refused.")
    import torch
    from ultralytics import YOLO
    if str(args.device).lower() != "cpu" and not torch.cuda.is_available():
        raise SystemExit(f"CUDA device {args.device!r} requested, but CUDA is unavailable")
    config = {"data": str(args.data.resolve()), "model": args.model, "epochs": args.epochs, "imgsz": args.imgsz,
              "device": args.device, "project": str(args.output.resolve()), "name": args.name,
              "started_utc": datetime.now(timezone.utc).isoformat()}
    print(json.dumps(config, indent=2)); args.output.mkdir(parents=True, exist_ok=True)
    (args.output / f"{args.name}_training_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    YOLO(args.model).train(data=str(args.data.resolve()), epochs=args.epochs, imgsz=args.imgsz, device=args.device,
                           project=str(args.output.resolve()), name=args.name, patience=15, seed=42)


if __name__ == "__main__": main()
