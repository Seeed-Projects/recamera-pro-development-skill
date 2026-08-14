# RKNN model conversion

## Contents

- [Fixed conversion contract](#fixed-conversion-contract)
- [End-to-end workflow](#end-to-end-workflow)
- [Inspect the ONNX model](#inspect-the-onnx-model)
- [Define preprocessing](#define-preprocessing)
- [Choose FP16 or quantization](#choose-fp16-or-quantization)
- [Prepare an INT8 dataset](#prepare-an-int8-dataset)
- [Convert the model](#convert-the-model)
- [Advanced conversion options](#advanced-conversion-options)
- [Validate numerical behavior](#validate-numerical-behavior)
- [Validate on the device](#validate-on-the-device)
- [Failure triage](#failure-triage)

## Fixed conversion contract

- Host: x86_64 Linux or WSL
- Conda environment: `recamera-rknn-2.3.2`
- Python: 3.10
- RKNN-Toolkit2: exactly 2.3.2
- ONNX and ONNX Runtime: exactly 1.18.0
- RKNN target: `rv1126b`
- Input model: ONNX
- Output model: `.rknn` plus `.rknn.json` provenance metadata
- Device RKNN Runtime: 2.3.2

Keep model conversion on x86_64 separate from aarch64 native application compilation. Do not use `rknn-toolkit-lite2` for conversion.

Conversion itself is an offline host operation. It does not require a connected reCamera Pro, the bundled `librknnrt.so`, an aarch64 compiler, a sysroot, SSH, or execution of the output model. RKNN-Toolkit2 compiles the ONNX graph into an `.rknn` targeted by `RKNN.config(target_platform='rv1126b')`.

Prepare the environment once, then verify it without network changes:

```bash
./scripts/setup_rknn_env.sh
./scripts/setup_rknn_env.sh --check
```

The setup path downloads the official 2.3.2 x86_64 CPython 3.10 wheel and its requirements. The check path verifies exact package versions and imports Toolkit2 without installing anything.

## End-to-end workflow

1. Record the source repository, license, export command, source checksum, preprocessing, output semantics, and intended postprocessing.
2. Run `inspect_onnx.py`; resolve invalid graphs and unexpected dynamic dimensions before conversion.
3. Establish a non-quantized FP16 baseline.
4. When the user requests only conversion, stop after exporting `.rknn` and `.rknn.json` and report their checksums.
5. If INT8 is required, create a deterministic representative dataset and convert with quantization.
6. Optionally compare FP16 and INT8 outputs when accuracy validation is requested. Use Toolkit layer accuracy analysis when error localization is needed.
7. Run the exported `.rknn` on reCamera Pro only when runtime or device validation is explicitly requested.

For a conversion-only task, `rknn.build` and `rknn.export_rknn` returning success, a non-empty output, recorded SHA-256, and `target_platform=rv1126b` are the completion criteria. This establishes successful compilation, not task-level accuracy or NPU runtime behavior.

## Inspect the ONNX model

```bash
conda run -n recamera-rknn-2.3.2 python scripts/inspect_onnx.py \
  model.onnx --json model.onnx.inspect.json --require-static
```

The report contains:

- ONNX checker result
- source SHA-256
- IR and opset versions
- true graph inputs, excluding initializers
- input/output names, types, shapes, and dynamic dimensions
- operator counts
- external-data usage

The tool does not claim that every ONNX operator is supported by RV1126B. Toolkit conversion remains the authoritative compatibility test. Preserve the source export code because unsupported operators often need re-export rather than graph patching.

For ordinary fixed-camera inference, prefer static batch-1 input shapes. When the model contains symbolic dimensions, either provide matching static overrides:

```bash
--input-name images --input-size 1,3,640,640
```

or deliberately supply Toolkit2 `dynamic_input` JSON. Do not silently invent a shape.

## Define preprocessing

Before conversion, determine all of the following from the original model implementation:

- NCHW or NHWC
- RGB or BGR
- input dtype and numeric range
- stretch, crop, or letterbox resize
- channel mean and standard deviation
- whether normalization already exists inside the ONNX graph
- output tensor names and postprocessing semantics

Toolkit applies normalization as `(input - mean) / std`. For the common conversion from unsigned pixels `[0,255]` to floats `[0,1]`, use:

```bash
--mean 0,0,0 --std 255,255,255
```

If preprocessing is embedded in ONNX, use identity normalization rather than applying it twice:

```bash
--mean 0,0,0 --std 1,1,1
```

Repeat `--mean` and `--std` once per input for multi-input models. `--rgb-to-bgr` changes image channel order used for quantization calibration; it does not replace an explicit runtime color-order contract.

## Choose FP16 or quantization

### FP16 baseline

Omit `--dataset`. Toolkit2 builds a non-quantized `float16` RKNN model. Always create this baseline first unless the model is already known and tested.

### Quantized model

Supplying `--dataset` enables quantization. Defaults are:

```text
quantized_dtype     w8a8
quantized_algorithm normal
quantized_method    channel
```

Do not choose a more exotic dtype merely because Toolkit accepts it. Confirm RV1126B operator support, accuracy, memory use, and runtime performance. `mmse`, `kl_divergence`, and automatic hybrid quantization are experiments to measure, not automatic improvements.

## Prepare an INT8 dataset

Use inputs representative of deployment lighting, backgrounds, object sizes, camera noise, and failure cases. Keep validation samples separate from calibration samples.

Create a deterministic single-input dataset list:

```bash
conda run -n recamera-rknn-2.3.2 python scripts/create_calibration_dataset.py \
  calibration/images calibration/dataset.txt \
  --recursive --limit 200 --seed 42
```

Supported entries are BMP, JPEG, PNG, and NPY. The script sorts inputs deterministically, optionally selects a seeded subset, rejects whitespace in paths, and writes absolute paths by default. Use `--relative` only when the data is below the list file directory and the directory layout will be preserved.

For multi-input models, construct the dataset according to Toolkit2's multi-input list format and validate every referenced file. The helper deliberately handles only single-input lists to avoid guessing input pairing.

`convert_onnx.py` refuses an empty dataset and checks that every referenced path exists. It records the dataset-list SHA-256 and sample count, but not copies of private calibration data.

## Convert the model

FP16 baseline:

```bash
conda run -n recamera-rknn-2.3.2 python scripts/convert_onnx.py \
  model.onnx model-fp16.rknn \
  --mean 0,0,0 --std 255,255,255
```

INT8:

```bash
conda run -n recamera-rknn-2.3.2 python scripts/convert_onnx.py \
  model.onnx model-int8.rknn \
  --dataset calibration/dataset.txt \
  --mean 0,0,0 --std 255,255,255
```

The converter runs the ONNX checker, rejects unresolved dynamic input dimensions, prevents accidental output replacement unless `--force` is supplied, and writes `MODEL.rknn.json`. Metadata includes source/output hashes, graph contract, preprocessing, quantization, optimization, dynamic-input, selected outputs, dataset provenance, and accuracy-analysis inputs.

## Advanced conversion options

Use `python scripts/convert_onnx.py --help` for the complete interface. Supported Toolkit2 2.3.2 controls include:

```text
--quantized-dtype
--quantized-algorithm
--quantized-method
--optimization-level
--rgb-to-bgr
--dynamic-input
--rknn-batch-size
--auto-hybrid
--compress-weight
--model-pruning
--custom-string
--output-name
```

Repeat `--input-name`, `--input-size`, and `--output-name` where applicable. Use either static input overrides or `--dynamic-input`, never both. Dynamic input accepts a JSON string or a JSON file containing the exact `RKNN.config(dynamic_input=...)` structure.

Automatic hybrid quantization requires a calibration dataset. Weight compression and pruning can change build behavior; compare accuracy and device performance before retaining them.

Run Toolkit layer accuracy analysis during conversion when a representative image or NPY tensor is available:

```bash
conda run -n recamera-rknn-2.3.2 python scripts/convert_onnx.py \
  model.onnx model-int8.rknn \
  --dataset calibration/dataset.txt \
  --mean 0,0,0 --std 255,255,255 \
  --accuracy-input validation/sample.npy \
  --accuracy-output-dir snapshot
```

This invokes Toolkit2 analysis on the host. Passing an actual RV1126B target requires a Toolkit-supported device transport and is separate from the skill's SSH deployment workflow.

## Optional: validate numerical behavior

Prepare one `.npy` array for each ONNX input. Arrays represent raw inputs supplied to RKNN; by default the comparison tool applies the recorded mean/std to the ONNX side so both paths see equivalent model-domain values.

```bash
conda run -n recamera-rknn-2.3.2 python scripts/compare_onnx_rknn.py \
  model.onnx model-fp16.rknn \
  --input images=validation/input.npy \
  --data-format nchw \
  --report comparison-fp16.json
```

Repeat `--input` and `--data-format` for multi-input models. Use `--no-onnx-preprocess` only when NPY arrays are already normalized model-domain tensors and should be fed identically to both APIs.

The report includes output shape matching, MAE, RMSE, maximum absolute error, and cosine similarity. Evaluate thresholds per model and output meaning; there is no universal acceptable cosine or MAE.

Toolkit2 2.3.2 cannot load an exported RV1126B `.rknn` into the host simulator. Therefore, the comparison tool:

1. verifies the `.rknn` and ONNX hashes against `.rknn.json`;
2. rebuilds the ONNX model using the recorded conversion configuration;
3. runs that build in the Toolkit simulator;
4. compares it with ONNX Runtime.

This validates conversion configuration reproducibility, not the bytes executing on the NPU.

## Optional: validate on the device

Final acceptance must execute the exported `.rknn` using the bundled 2.3.2 C API contract and the board's `/oem/usr/lib/librknnrt.so`. Validate:

- `rknn_init` and tensor queries
- actual input dtype, format, size, and quantization attributes
- preprocessing parity with the conversion metadata
- decoded predictions on held-out samples
- latency after warm-up, not only the first run
- memory use and sustained operation

Compare task-level results such as classifications, boxes, masks, keypoints, or embeddings—not only raw tensor distance.

## Failure triage

- **ONNX checker failure:** fix the exporter or external-data layout before invoking Toolkit.
- **Unsupported operator:** re-export or simplify using a semantically equivalent supported form; never delete an operator to make conversion pass.
- **Dynamic input rejection:** provide verified static overrides or an explicit dynamic-input profile.
- **`onnx.mapping` error:** verify ONNX 1.18.0 rather than 1.19 or later.
- **Quantization build failure:** validate dataset paths, input count, dtype, shape, and preprocessing.
- **Accuracy regression:** compare resize/letterbox, layout, RGB/BGR, mean/std, output ordering, calibration coverage, and postprocessing first.
- **Simulator mismatch:** verify `--data-format` and whether NPY inputs are raw or already normalized.
- **Device mismatch:** compare `.rknn` checksum, Toolkit/Runtime 2.3.2, queried tensor attributes, and board preprocessing.
- **Performance regression:** measure on-device after warm-up and inspect NPU/CPU operator placement; simulator time is not device performance.
