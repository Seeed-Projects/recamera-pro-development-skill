#!/usr/bin/env python3
"""Convert an ONNX model to RKNN Toolkit2 2.3.2 for RV1126B."""

import argparse
import hashlib
import json
import shlex
from collections import Counter
from pathlib import Path

def csv_numbers(value: str) -> list[float]:
    try:
        values = [float(item.strip()) for item in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected comma-separated numbers") from error
    if not values:
        raise argparse.ArgumentTypeError("expected at least one number")
    return values


def shape(value: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected comma-separated dimensions") from error
    if not values or any(item <= 0 for item in values):
        raise argparse.ArgumentTypeError("expected positive comma-separated dimensions")
    return values


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tensor_shape(value_info) -> list[int | str | None]:
    dimensions = []
    for dimension in value_info.type.tensor_type.shape.dim:
        if dimension.HasField("dim_value"):
            dimensions.append(dimension.dim_value)
        elif dimension.HasField("dim_param"):
            dimensions.append(dimension.dim_param)
        else:
            dimensions.append(None)
    return dimensions


def model_summary(path: Path) -> dict:
    import onnx

    model = onnx.load(str(path), load_external_data=False)
    onnx.checker.check_model(model)
    initializer_names = {item.name for item in model.graph.initializer}
    inputs = [item for item in model.graph.input if item.name not in initializer_names]
    return {
        "ir_version": model.ir_version,
        "opsets": [
            {"domain": item.domain or "ai.onnx", "version": item.version}
            for item in model.opset_import
        ],
        "inputs": [{"name": item.name, "shape": tensor_shape(item)} for item in inputs],
        "outputs": [
            {"name": item.name, "shape": tensor_shape(item)} for item in model.graph.output
        ],
        "operator_counts": dict(sorted(Counter(node.op_type for node in model.graph.node).items())),
    }


def parse_dynamic_input(value: str | None):
    if not value:
        return None
    if value.lstrip().startswith("["):
        raw = value
    else:
        candidate = Path(value)
        raw = candidate.read_text(encoding="utf-8") if candidate.is_file() else value
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(f"invalid dynamic-input JSON: {error}") from error
    if not isinstance(parsed, list) or not parsed:
        raise argparse.ArgumentTypeError("dynamic-input must be a non-empty JSON list")
    return parsed


def inspect_dataset(path: Path | None) -> dict | None:
    if path is None:
        return None
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    lines = [line for line in lines if line and not line.startswith("#")]
    if not lines:
        raise ValueError(f"calibration dataset is empty: {path}")
    missing = []
    for line in lines:
        for token in shlex.split(line):
            candidate = Path(token)
            if not candidate.is_absolute():
                candidate = path.parent / candidate
            if not candidate.is_file():
                missing.append(str(candidate))
    if missing:
        preview = "\n  ".join(missing[:10])
        raise ValueError(f"calibration dataset references missing files:\n  {preview}")
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "samples": len(lines),
    }


def require_success(code: int, operation: str) -> None:
    if code != 0:
        raise RuntimeError(f"{operation} failed: {code}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert ONNX to RKNN Toolkit2 2.3.2 for reCamera Pro RV1126B"
    )
    parser.add_argument("onnx", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dataset", type=Path, help="calibration list; enables quantization")
    parser.add_argument("--mean", action="append", type=csv_numbers, required=True, help="repeat for multi-input models")
    parser.add_argument("--std", action="append", type=csv_numbers, required=True, help="repeat for multi-input models")
    parser.add_argument("--input-name", action="append", default=[])
    parser.add_argument("--input-size", action="append", type=shape, default=[])
    parser.add_argument("--output-name", action="append", default=[])
    parser.add_argument("--quantized-dtype", default="w8a8", choices=["w8a8", "w8a16", "w16a16i", "w16a16i_dfp", "w4a16"])
    parser.add_argument("--quantized-algorithm", default="normal", choices=["normal", "mmse", "kl_divergence", "gdq"])
    parser.add_argument("--quantized-method", default="channel", help="layer, channel, or group32..group256")
    parser.add_argument("--optimization-level", type=int, choices=range(0, 4), default=3)
    parser.add_argument("--float-dtype", default="float16", choices=["float16"])
    parser.add_argument("--rgb-to-bgr", action="store_true", help="swap calibration image channels")
    parser.add_argument("--dynamic-input", help="RKNN dynamic_input JSON string or JSON file")
    parser.add_argument("--rknn-batch-size", type=int)
    parser.add_argument("--auto-hybrid", action="store_true")
    parser.add_argument("--compress-weight", action="store_true")
    parser.add_argument("--model-pruning", action="store_true")
    parser.add_argument("--custom-string")
    parser.add_argument("--accuracy-input", action="append", type=Path, default=[], help="jpg/png/bmp/npy input for Toolkit layer accuracy analysis")
    parser.add_argument("--accuracy-output-dir", type=Path, default=Path("snapshot"))
    parser.add_argument("--force", action="store_true", help="replace an existing RKNN output")
    args = parser.parse_args()

    from rknn.api import RKNN

    if not args.onnx.is_file():
        parser.error(f"ONNX file not found: {args.onnx}")
    if len(args.mean) != len(args.std):
        parser.error("repeat --mean and --std the same number of times")
    for mean, std in zip(args.mean, args.std):
        if len(mean) != len(std):
            parser.error("each --mean and matching --std must contain the same number of values")
    if len(args.input_name) != len(args.input_size):
        parser.error("repeat --input-name and --input-size the same number of times")
    if args.dataset and not args.dataset.is_file():
        parser.error(f"dataset list not found: {args.dataset}")
    for accuracy_input in args.accuracy_input:
        if not accuracy_input.is_file():
            parser.error(f"accuracy input not found: {accuracy_input}")
    if args.output.exists() and not args.force:
        parser.error(f"output already exists: {args.output}; pass --force to replace it")
    if args.rknn_batch_size is not None and args.rknn_batch_size <= 0:
        parser.error("--rknn-batch-size must be positive")
    if args.auto_hybrid and args.dataset is None:
        parser.error("--auto-hybrid requires --dataset")
    if args.dynamic_input and args.input_name:
        parser.error("use either --dynamic-input or static --input-name/--input-size overrides, not both")
    if args.quantized_method not in {"layer", "channel"}:
        if not args.quantized_method.startswith("group"):
            parser.error("--quantized-method must be layer, channel, or group32..group256")
        try:
            group_size = int(args.quantized_method[5:])
        except ValueError:
            parser.error("invalid group quantization size")
        if group_size < 32 or group_size > 256 or group_size % 32:
            parser.error("group quantization size must be a multiple of 32 from 32 to 256")

    summary = model_summary(args.onnx)
    if len(args.mean) != len(summary["inputs"]):
        parser.error(
            f"repeat --mean/--std once per ONNX input; model has {len(summary['inputs'])} input(s)"
        )
    if len(set(args.input_name)) != len(args.input_name):
        parser.error("--input-name values must be unique")
    unknown_inputs = set(args.input_name) - {item["name"] for item in summary["inputs"]}
    if unknown_inputs:
        parser.error(f"unknown --input-name value(s): {sorted(unknown_inputs)}")
    dataset = inspect_dataset(args.dataset)
    dynamic_input = parse_dynamic_input(args.dynamic_input)
    if dynamic_input is None:
        dynamic_dimensions = [
            item for item in summary["inputs"] if any(not isinstance(dim, int) for dim in item["shape"])
        ]
        if dynamic_dimensions and not args.input_name:
            names = ", ".join(item["name"] for item in dynamic_dimensions)
            parser.error(
                f"dynamic input dimensions found for {names}; provide static --input-name/--input-size "
                "pairs or an explicit --dynamic-input configuration"
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rknn = RKNN(verbose=True)
    try:
        config = {
            "target_platform": "rv1126b",
            "mean_values": args.mean,
            "std_values": args.std,
            "quantized_dtype": args.quantized_dtype,
            "quantized_algorithm": args.quantized_algorithm,
            "quantized_method": args.quantized_method,
            "float_dtype": args.float_dtype,
            "optimization_level": args.optimization_level,
            "quant_img_RGB2BGR": args.rgb_to_bgr,
            "compress_weight": args.compress_weight,
            "model_pruning": args.model_pruning,
        }
        if dynamic_input is not None:
            config["dynamic_input"] = dynamic_input
        if args.custom_string:
            config["custom_string"] = args.custom_string
        require_success(rknn.config(**config), "rknn.config")

        load_kwargs = {"model": str(args.onnx)}
        if args.input_name:
            load_kwargs.update(inputs=args.input_name, input_size_list=args.input_size)
        if args.output_name:
            load_kwargs["outputs"] = args.output_name
        require_success(rknn.load_onnx(**load_kwargs), "rknn.load_onnx")

        quantized = args.dataset is not None
        require_success(
            rknn.build(
                do_quantization=quantized,
                dataset=str(args.dataset) if quantized else None,
                rknn_batch_size=args.rknn_batch_size,
                auto_hybrid=args.auto_hybrid,
            ),
            "rknn.build",
        )
        if args.accuracy_input:
            args.accuracy_output_dir.mkdir(parents=True, exist_ok=True)
            result = rknn.accuracy_analysis(
                inputs=[str(item) for item in args.accuracy_input],
                output_dir=str(args.accuracy_output_dir),
                target=None,
            )
            if result not in (None, 0):
                raise RuntimeError(f"rknn.accuracy_analysis failed: {result}")
        require_success(rknn.export_rknn(str(args.output)), "rknn.export_rknn")
    finally:
        rknn.release()

    metadata = {
        "schema_version": 2,
        "toolkit_version": "2.3.2",
        "target_platform": "rv1126b",
        "source": str(args.onnx.resolve()),
        "source_sha256": sha256(args.onnx),
        "output": str(args.output.resolve()),
        "output_sha256": sha256(args.output),
        "onnx": summary,
        "quantized": args.dataset is not None,
        "dataset": dataset,
        "preprocessing": {
            "mean": args.mean,
            "std": args.std,
            "quant_img_RGB2BGR": args.rgb_to_bgr,
        },
        "inputs_override": [
            {"name": name, "size": size}
            for name, size in zip(args.input_name, args.input_size)
        ],
        "outputs_override": args.output_name,
        "build": {
            "quantized_dtype": args.quantized_dtype,
            "quantized_algorithm": args.quantized_algorithm,
            "quantized_method": args.quantized_method,
            "float_dtype": args.float_dtype,
            "optimization_level": args.optimization_level,
            "dynamic_input": dynamic_input,
            "rknn_batch_size": args.rknn_batch_size,
            "auto_hybrid": args.auto_hybrid,
            "compress_weight": args.compress_weight,
            "model_pruning": args.model_pruning,
            "custom_string": args.custom_string,
            "accuracy_inputs": [str(item.resolve()) for item in args.accuracy_input],
            "accuracy_output_dir": str(args.accuracy_output_dir.resolve()) if args.accuracy_input else None,
        },
    }
    metadata_path = args.output.with_suffix(args.output.suffix + ".json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} and {metadata_path}")


if __name__ == "__main__":
    main()
