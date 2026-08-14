#!/usr/bin/env python3
"""Validate an ONNX file and report its conversion contract."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe(value_info) -> dict:
    from onnx import TensorProto

    tensor = value_info.type.tensor_type
    dimensions = []
    for dimension in tensor.shape.dim:
        if dimension.HasField("dim_value"):
            dimensions.append(dimension.dim_value)
        elif dimension.HasField("dim_param"):
            dimensions.append(dimension.dim_param)
        else:
            dimensions.append(None)
    return {
        "name": value_info.name,
        "dtype": TensorProto.DataType.Name(tensor.elem_type),
        "shape": dimensions,
        "dynamic": any(not isinstance(item, int) for item in dimensions),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect and validate an ONNX model before RKNN conversion")
    parser.add_argument("model", type=Path)
    parser.add_argument("--json", type=Path, help="also write the report as JSON")
    parser.add_argument("--require-static", action="store_true")
    args = parser.parse_args()

    import onnx
    from onnx import TensorProto

    if not args.model.is_file():
        parser.error(f"model not found: {args.model}")
    model = onnx.load(str(args.model), load_external_data=False)
    onnx.checker.check_model(model)
    initializers = {item.name for item in model.graph.initializer}
    inputs = [describe(item) for item in model.graph.input if item.name not in initializers]
    outputs = [describe(item) for item in model.graph.output]
    report = {
        "path": str(args.model.resolve()),
        "sha256": sha256(args.model),
        "ir_version": model.ir_version,
        "opsets": [
            {"domain": item.domain or "ai.onnx", "version": item.version}
            for item in model.opset_import
        ],
        "inputs": inputs,
        "outputs": outputs,
        "node_count": len(model.graph.node),
        "initializer_count": len(model.graph.initializer),
        "operator_counts": dict(sorted(Counter(node.op_type for node in model.graph.node).items())),
        "external_data": any(
            tensor.data_location == TensorProto.EXTERNAL for tensor in model.graph.initializer
        ),
    }
    print(json.dumps(report, indent=2))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.require_static and any(item["dynamic"] for item in inputs):
        parser.error("model contains dynamic input dimensions")


if __name__ == "__main__":
    main()
