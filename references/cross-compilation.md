# Cross-compilation contract

## Install Seeed's official SDK

Use the official [reCamera Pro SDK](https://github.com/Seeed-Projects/recamera_pro_sdk) for its matched RV1126B GCC 12.4 toolchain and target sysroot. The repository holds the integration scripts; `setup.sh` downloads roughly 2.5 GB of versioned release assets, verifies SHA-256 before extraction, and is idempotent. Ask for authorization before installing host packages or downloading those assets.

```bash
sudo apt install cmake ninja-build pkg-config
git clone https://github.com/Seeed-Projects/recamera_pro_sdk.git
cd recamera_pro_sdk
./scripts/setup.sh
source scripts/env.sh
bash scripts/check-sdk.sh
```

`source scripts/env.sh` exports `RECAMERA_SYSROOT` and `RECAMERA_CROSS_PREFIX` (as well as `CC`, `CXX`, and target-only `pkg-config` paths). Keep that shell active when invoking this skill's `scripts/build_app.sh`, or source the SDK environment again in each new shell. Do not place the SDK's generated `toolchain/` or `sysroot/` inside a Skill repository.

## Required local inputs

Set these variables before building:

```bash
export RECAMERA_SYSROOT=/absolute/path/to/recamera-pro-sysroot
export RECAMERA_CROSS_PREFIX=/absolute/path/to/bin/aarch64-linux-gnu-
```

The skill bundles Seeed's production reCamera Pro RKNN Runtime 2.3.2 at `assets/recamera-pro-runtime/librknnrt.so`. It is the only permitted cross-link library. `scripts/build_app.sh` validates it against `SHA256SUMS` and rejects `RECAMERA_RKNNRT` and `RECAMERA_RKNN_RUNTIME_DIR` overrides. The production device loads the matching `/oem/usr/lib/librknnrt.so` at runtime.

The sysroot must contain target headers and libraries for libc, libstdc++, GStreamer 1.0, GLib 2.0, and their transitive build metadata. Prefer the reCamera Pro/RV1126B vendor SDK sysroot. If the sysroot was mirrored from a live device, preserve symlinks.

## GStreamer pkg-config

The build script sets:

```bash
PKG_CONFIG_SYSROOT_DIR="$RECAMERA_SYSROOT"
PKG_CONFIG_LIBDIR="$RECAMERA_SYSROOT/usr/lib/aarch64-linux-gnu/pkgconfig:$RECAMERA_SYSROOT/usr/lib64/pkgconfig:$RECAMERA_SYSROOT/usr/lib/pkgconfig:$RECAMERA_SYSROOT/usr/share/pkgconfig"
```

If the vendor stores `.pc` files elsewhere, append that target directory. Never let `pkg-config` return `/usr/lib/x86_64-linux-gnu` or host include paths.

## Runtime dependencies

The minimal template requires:

- `librknnrt.so` at `/oem/usr/lib/librknnrt.so`
- GStreamer core and app libraries
- GStreamer plugins used by the pipeline: `v4l2src`, caps handling, `videoconvert`, and `appsink`
- GLib and normal C/C++ runtime dependencies

The plugins are loaded dynamically and may not appear in `DT_NEEDED`; verify them on the device with `gst-inspect-1.0` when the user runs the program.

For a C/C++ RTSP server, the sysroot additionally needs matching `gstreamer-rtsp-server-1.0` headers, `.pc` metadata, and target libraries. The verified current firmware has `libgstrtspserver-1.0.so.0.2206.0`, but its production rootfs has no development headers or `.pc` file. Obtain those compile-time files from the matching SDK or a compatible target development package. Verify the board separately after firmware changes and inspect all transitive `DT_NEEDED` entries.

## ABI validation

Run these on the produced executable:

```bash
file build/recamera_rknn_gst
aarch64-linux-gnu-readelf -l build/recamera_rknn_gst | grep interpreter
aarch64-linux-gnu-readelf -d build/recamera_rknn_gst
aarch64-linux-gnu-objdump -p build/recamera_rknn_gst | grep NEEDED
```

Compare the ELF interpreter and maximum GLIBC/GLIBCXX symbol requirements with the device or sysroot. If they exceed the board versions, rebuild with the vendor toolchain/sysroot; static linking does not solve proprietary RKNN/GStreamer plugin ABI compatibility.

## Capture and preprocessing

Probe the camera separately before debugging NPU code:

```bash
gst-launch-1.0 -v v4l2src device=/dev/video13 num-buffers=30 \
  ! 'video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1' \
  ! videoconvert ! fakesink
```

For inference, the template converts NV12 to RGB and resizes to the CLI dimensions before `appsink`. Change RGB to BGR only when the model contract requires it. Letterboxing is model-specific and is not implemented by the starter template.
