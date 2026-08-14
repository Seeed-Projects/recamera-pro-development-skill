#!/usr/bin/env python3
"""Compare ONNX Runtime outputs with RKNN Toolkit2 simulator outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

def input_binding(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected INPUT_NAME=ARRAY.npy")
    name, path = value.split("=", 1)
    if not name or not path:
        raise argparse.ArgumentTypeError("expected INPUT_NAME=ARRAY.npy")
    return name, Path(path)


def metrics(reference: np.ndarray, candidate: np.ndarray) -> dict:
    import numpy as np

    reference = np.asarray(reference, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    if reference.shape != candidate.shape:
        return {"shape_match": False, "reference_shape": list(reference.shape), "rknn_shape": list(candidate.shape)}
    delta = candidate - reference
    ref_flat = reference.ravel()
    candidate_flat = candidate.ravel()
    denominator = np.linalg.norm(ref_flat) * np.linalg.norm(candidate_flat)
    cosine = float(np.dot(ref_flat, candidate_flat) / denominator) if denominator else None
    return {
        "shape_match": True,
        "shape": list(reference.shape),
        "mae": float(np.mean(np.abs(delta))),
        "rmse": float(np.sqrt(np.mean(np.square(delta)))),
        "max_abs_error": float(np.max(np.abs(delta))),
        "cosine_similarity": cosine,
    }


def require_success(code: int, operation: str) -> None:
    if code != 0:
        raise RuntimeError(f"{operation} failed: {code}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preprocess_for_onnx(array: np.ndarray, mean: list[float], std: list[float], data_format: str | None) -> np.ndarray:
    import numpy as np

    array = np.asarray(array, dtype=np.float32)
    if len(mean) == 1:
        return (array - mean[0]) / std[0]
    if array.ndim != 4:
        raise ValueError("multi-channel preprocessing comparison requires a 4D input")
    layout = data_format or "nhwc"
    channel_axis = 1 if layout == "nchw" else 3
    if array.shape[channel_axis] != len(mean):
        raise ValueError(
            f"input channel dimension {array.shape[channel_axis]} does not match mean/std length {len(mean)}"
        )
    broadcast_shape = [1] * array.ndim
    broadcast_shape[channel_axis] = len(mean)
    mean_array = np.asarray(mean, dtype=np.float32).reshape(broadcast_shape)
    std_array = np.asarray(std, dtype=np.float32).reshape(broadcast_shape)
    return np.asarray((array - mean_array) / std_array, dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild an RKNN model from conversion metadata and compare simulator outputs with ONNX Runtime")
    parser.add_argument("onnx", type=Path)
    parser.add_argument("rknn", type=Path)
    parser.add_argument("--input", action="append", type=input_binding, required=True)
    parser.add_argument("--data-format", action="append", choices=["nchw", "nhwc"])
    parser.add_argument("--report", type=Path)
    parser.add_argument("--no-onnx-preprocess", action="store_true", help="feed identical arrays to ONNX instead of applying RKNN mean/std")
    args = parser.parse_args()

    import numpy as np
    import onnxruntime as ort
    from rknn.api import RKNN

    for path in (args.onnx, args.rknn):
        if not path.is_file():
            parser.error(f"file not found: {path}")
    metadata_path = args.rknn.with_suffix(args.rknn.suffix + ".json")
    if not metadata_path.is_file():
        parser.error(f"conversion metadata not found: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("output_sha256") != sha256(args.rknn):
        parser.error("RKNN checksum does not match its conversion metadata")
    if metadata.get("source_sha256") != sha256(args.onnx):
        parser.error("ONNX checksum does not match the conversion metadata")

    arrays = []
    raw_feed = {}
    for name, path in args.input:
        if not path.is_file():
            parser.error(f"input array not found: {path}")
        array = np.load(path, allow_pickle=False)
        raw_feed[name] = array
        arrays.append(array)
    formats = args.data_format
    if formats is not None and len(formats) != len(arrays):
        parser.error("repeat --data-format once for every --input")

    session = ort.InferenceSession(str(args.onnx), providers=["CPUExecutionProvider"])
    expected_names = [item.name for item in session.get_inputs()]
    if set(raw_feed) != set(expected_names):
        parser.error(f"input names must match ONNX inputs: {expected_names}")
    preprocessing = metadata["preprocessing"]
    onnx_feed = {}
    for index, name in enumerate(expected_names):
        if args.no_onnx_preprocess:
            onnx_feed[name] = raw_feed[name]
        else:
            current_format = formats[index] if formats else None
            onnx_feed[name] = preprocess_for_onnx(
                raw_feed[name], preprocessing["mean"][index], preprocessing["std"][index], current_format
            )
    onnx_outputs = session.run(None, onnx_feed)

    runtime = RKNN(verbose=True)
    try:
        build = metadata["build"]
        config = {
            "target_platform": "rv1126b",
            "mean_values": preprocessing["mean"],
            "std_values": preprocessing["std"],
            "quantized_dtype": build["quantized_dtype"],
            "quantized_algorithm": build["quantized_algorithm"],
            "quantized_method": build["quantized_method"],
            "float_dtype": build["float_dtype"],
            "optimization_level": build["optimization_level"],
            "quant_img_RGB2BGR": preprocessing["quant_img_RGB2BGR"],
            "compress_weight": build["compress_weight"],
            "model_pruning": build["model_pruning"],
        }
        for key in ("dynamic_input", "custom_string"):
            if build.get(key) is not None:
                config[key] = build[key]
        require_success(runtime.config(**config), "rknn.config")
        load_kwargs = {"model": str(args.onnx)}
        if metadata["inputs_override"]:
            load_kwargs["inputs"] = [item["name"] for item in metadata["inputs_override"]]
            load_kwargs["input_size_list"] = [item["size"] for item in metadata["inputs_override"]]
        if metadata["outputs_override"]:
            load_kwargs["outputs"] = metadata["outputs_override"]
        require_success(runtime.load_onnx(**load_kwargs), "rknn.load_onnx")
        dataset = metadata.get("dataset")
        require_success(
            runtime.build(
                do_quantization=metadata["quantized"],
                dataset=dataset["path"] if dataset else None,
                rknn_batch_size=build["rknn_batch_size"],
                auto_hybrid=build["auto_hybrid"],
            ),
            "rknn.build",
        )
        require_success(runtime.init_runtime(target=None), "rknn.init_runtime(simulator)")
        ordered_arrays = [raw_feed[name] for name in expected_names]
        rknn_outputs = runtime.inference(inputs=ordered_arrays, data_format=formats)
    finally:
        runtime.release()
    if len(onnx_outputs) != len(rknn_outputs):
        raise RuntimeError(f"output count mismatch: ONNX={len(onnx_outputs)}, RKNN={len(rknn_outputs)}")

    output_names = [item.name for item in session.get_outputs()]
    report = {
        "runtime": "RKNN Toolkit2 simulator rebuilt from conversion metadata",
        "artifact_note": "The exported .rknn checksum was verified, but Toolkit2 simulator cannot load the exported RV1126B artifact; final validation must run on-device.",
        "onnx_preprocessing_applied": not args.no_onnx_preprocess,
        "inputs": [{"name": name, "shape": list(raw_feed[name].shape), "dtype": str(raw_feed[name].dtype)} for name in expected_names],
        "outputs": [
            {"index": index, "name": name, **metrics(reference, candidate)}
            for index, (name, reference, candidate) in enumerate(zip(output_names, onnx_outputs, rknn_outputs))
        ],
    }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
