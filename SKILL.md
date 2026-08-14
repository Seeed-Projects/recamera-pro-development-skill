---
name: recamera-rknn-dev
description: Develop native AI and multimedia applications for Seeed reCamera Pro (RV1126B, aarch64) from Linux or WSL. Use when Gemini CLI needs to inspect a reCamera Pro or its build environment, convert ONNX models to RKNN, create or cross-compile C/C++ RKNN Runtime applications, capture camera or microphone input, play sound through the speaker, publish inference video with GStreamer/RTSP, construct a target sysroot, or diagnose architecture, ABI, linker, audio, video, GStreamer, RTSP, model-conversion, and NPU-runtime problems.
---

# reCamera Pro RKNN Development

Build and convert in WSL for the 64-bit ARM reCamera Pro. Keep model conversion (x86_64 Python) separate from target compilation (aarch64 C/C++).

## Fixed target contract

- Treat the device as reCamera **Pro**, SoC `RV1126B`, OS architecture `aarch64`. Never use SG2002/riscv64 reCamera instructions.
- Pin RKNN-Toolkit2 to `2.3.2` and configure conversion with `target_platform='rv1126b'`.
- Treat Seeed production reCamera Pro as a fixed RKNN 2.3.2 platform contract: RKNN-Toolkit2, `rknn_api.h`, model conversion, and RKNN Runtime must all use 2.3.2.
- Link only with the bundled, Seeed-qualified `assets/recamera-pro-runtime/librknnrt.so`. `scripts/build_app.sh` verifies SHA-256 before configuring the build and rejects `RECAMERA_RKNNRT` overrides. Never download or substitute another RKNN Runtime.
- Expect the same library at `/oem/usr/lib/librknnrt.so` on production devices and embed `/oem/usr/lib` as the runtime search path. Do not copy over or replace the board library.
- Use GStreamer for capture. The known camera probe is:

```bash
gst-launch-1.0 -v v4l2src device=/dev/video13 num-buffers=30 \
  ! 'video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1' \
  ! videoconvert ! fakesink
```

- Treat device paths and plugin availability as firmware-specific. Run `scripts/inspect_device.sh HOST` when SSH access is explicitly authorized, and save its output with the project.

## Workflow

1. Run `scripts/inspect_wsl.sh`. When device access is authorized, also run `scripts/inspect_device.sh root@HOST`. Do not install or build until the host, compiler, sysroot, media devices, and target plugins are known. If inspecting a production device, compare its RKNN library SHA-256 with the bundled manifest and stop on mismatch.
2. For model conversion, read `references/model-conversion.md`, run `scripts/setup_rknn_env.sh`, then use `--check` to verify the pinned environment without network changes. It reuses Conda when available, otherwise installs Miniforge without root and creates `recamera-rknn-2.3.2`.
3. Obtain model files only from an authoritative or user-approved source. Preserve the source URL, license, export command, checksum, input layout, normalization, color order, resize policy, output semantics, and postprocessing. Never guess these values.
4. Inspect ONNX with `scripts/inspect_onnx.py`. Resolve invalid graphs and unexpected dynamic inputs before conversion. For INT8, create a deterministic representative list with `scripts/create_calibration_dataset.py`; keep validation data separate.
5. Convert ONNX with `scripts/convert_onnx.py`. Establish FP16 first unless the user explicitly requests INT8, then evaluate quantization or advanced optimization deliberately. Preserve the generated `.rknn.json` beside the model. For a conversion-only request, successful export with `target_platform='rv1126b'` completes the requested artifact; no device connection or RKNN Runtime library is needed.
6. Run `scripts/compare_onnx_rknn.py`, Toolkit accuracy analysis, or on-device inference only when the user requests accuracy or runtime validation. These are optional validation workflows, not prerequisites for producing an RV1126B `.rknn`.
7. For native code, run `scripts/create_project.sh PROJECT_DIR` to copy `assets/rknn-gst-app/` and fetch the matching 2.3.2 `rknn_api.h`. Read `references/cross-compilation.md` before configuring it.
8. Require a target-compatible aarch64 compiler and sysroot. Prefer the vendor SDK toolchain/sysroot. A generic Ubuntu cross compiler is acceptable only after its glibc/libstdc++ requirements are verified against the board.
9. For microphone, speaker, or streaming work, read `references/device-audio-rtsp.md`. Do not assume `alsasrc`, `alsasink`, an encoder, RTSP development headers, or pkg-config metadata exists merely because GStreamer, ALSA, and an RTSP runtime library exist.
10. Build with `scripts/build_app.sh`, then require all checks to pass:
   - `file` reports ARM aarch64, not x86-64 or RISC-V.
   - `readelf -d` shows `NEEDED` for `librknnrt.so` and GStreamer libraries.
   - RUNPATH/RPATH contains `/oem/usr/lib`.
   - no build-tree or WSL absolute paths appear in runtime search paths.
11. Hand the executable, `.rknn`, `.rknn.json`, validation report, invocation, expected input/output contract, and any non-firmware runtime dependencies to the user. Transfer or run on-device only when explicitly requested.

## Guardrails

- Do not use `rknn-toolkit-lite2` for board C/C++ applications; call the RKNN Runtime C API.
- Do not fetch `librknnrt.so` from the network, an SDK, RKNN Model Zoo, a package manager, or another board. Use the bundled 2.3.2 library and require its manifest checksum.
- Do not link the WSL host's x86_64 GStreamer or RKNN libraries into the target binary.
- Do not infer compatibility merely because the CPU is aarch64. Validate libc, C++ ABI, ELF interpreter, and every target dependency against the sysroot/board.
- Do not feed NV12 bytes directly to an RGB/BGR model. Make the GStreamer pipeline produce the exact model input format and size, or implement explicit preprocessing.
- Do not stop `rkipc`, audio services, or other device processes just to obtain a device node. Report ownership and coordinate resource sharing or an explicitly authorized service stop.
- Do not deploy host-distribution GStreamer plugins or RTSP libraries without matching the target GStreamer 1.22 ABI and validating every transitive dependency.
- Keep quantization images representative and list them one path per line. Calibration data is required for INT8.
- Do not claim accuracy or runtime correctness from conversion alone. For a conversion-only request, report that the artifact was successfully compiled for RV1126B and clearly distinguish this from optional accuracy or device validation.
- Do not attempt to run the `.rknn` when the user only asks for model conversion. If optional simulator validation is requested, do not describe it as execution of the exported RV1126B artifact.
- If a downloaded model or dependency has no clear redistribution/license terms, download for the user's local use only and do not bundle it into the Skill.

## References and reusable resources

- Read `references/model-conversion.md` for conversion decisions and compatibility notes.
- Read `references/cross-compilation.md` for sysroot, toolchain, GStreamer, and ELF validation details.
- Read `references/device-audio-rtsp.md` for verified firmware facts, ALSA microphone/speaker workflows, resource conflicts, and RTSP architecture choices.
- Run `scripts/inspect_device.sh root@HOST` for a read-only, repeatable target inventory before relying on device numbers or plugin names.
- Use `assets/recamera-pro-runtime/librknnrt.so` as the sole cross-link RKNN Runtime. Its SHA-256 is recorded in the adjacent `SHA256SUMS`.
- Use `assets/rknn-gst-app/` as a minimal single-input RKNN + GStreamer starting point. Adapt preprocessing and postprocessing to the actual model rather than presenting the template as a complete detector.
