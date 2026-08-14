# Device audio and RTSP

## Verified baseline

The following facts were observed on a reCamera Pro firmware image dated 2026-07-20. Re-run `scripts/inspect_device.sh root@HOST` after every firmware change; do not treat them as universal constants.

- OS: Buildroot 2023.02.6, aarch64, glibc 2.38.
- GStreamer: 1.22.6.
- Camera capture: `/dev/video13` supports NV12 and other raw formats up to 3840x2160.
- ALSA card 0: `rockchiprv1126b`, PCM `hw:0,0`, one playback and one capture stream.
- PCM hardware contract: two channels, 16000 Hz, `S16_LE`, `S24_LE`, or `S32_LE`.
- RKNN Runtime: 2.3.2 at `/oem/usr/lib/librknnrt.so`; its verified production binary is bundled with the skill for cross-linking.
- Firmware RTSP: `rkipc` listens on `127.0.0.1:5554`; `go2rtc` republishes main/sub streams on port 554 and WebRTC on 8555.
- RTSP server runtime: `/usr/lib/libgstrtspserver-1.0.so.0.2206.0` is present, but the production rootfs has no corresponding headers or pkg-config metadata.
- Missing on this image: GStreamer `alsasrc`, `alsasink`, `opusenc`, and hardware H.264 encoder elements.

## Microphone capture

List cards and determine whether the PCM is already owned:

```bash
cat /proc/asound/cards
cat /proc/asound/pcm
fuser /dev/snd/pcmC0D0c
```

The firmware services may hold capture open. A `Device or resource busy` error is a resource conflict, not proof that the microphone is broken. Do not kill or stop the owner without explicit authorization. When capture is free, record the native format first:

```bash
arecord -D hw:0,0 -f S16_LE -r 16000 -c 2 -d 5 /tmp/mic.wav
```

For a native application, link `libasound` and use ALSA directly when `alsasrc` is absent. Configure interleaved access, 16000 Hz, two channels, and a supported sample format. Recover overruns with `snd_pcm_recover`; do not assume mono is accepted by the hardware. Downmix or resample in the application only after capture.

## Speaker playback

The speaker path has mixer controls including `Speaker`, `Power Amplifier`, `DAC Digital`, and `spk switch`. Inspect current state before changing anything:

```bash
amixer -c 0 sget Speaker
amixer -c 0 sget 'Power Amplifier'
amixer -c 0 sget 'DAC Digital'
amixer -c 0 sget 'spk switch'
```

Mixer changes are persistent device state and can produce loud output; make them only when the user asks. Test with a low-amplitude, two-channel, 16 kHz WAV:

```bash
aplay -D hw:0,0 /path/to/quiet-16k-stereo.wav
```

For C/C++, use ALSA directly when `alsasink` is absent. Convert arbitrary application audio to the hardware contract before `snd_pcm_writei`, and recover underruns.

## GStreamer audio implications

GStreamer core audio conversion does not provide hardware I/O. `audioconvert` and `audioresample` being present does not compensate for missing `alsasrc`/`alsasink`. Choose one of these designs:

1. Use ALSA in C/C++ for microphone/speaker and GStreamer for video/networking.
2. Cross-build the `gst-plugins-base` ALSA plugin against the exact target GStreamer 1.22.6 and ALSA ABI, then deploy the plugin plus all missing target dependencies under an application-owned plugin directory.
3. Use `appsrc`/`appsink` to bridge ALSA-owned buffers into or out of a GStreamer pipeline.

Set `GST_PLUGIN_PATH` to an application-owned directory for extra plugins. Never overwrite firmware plugins. Validate each plugin on-device with `gst-inspect-1.0` before constructing the pipeline.

## RTSP architecture

Distinguish three different tasks:

- **Consume RTSP:** use `rtspsrc`; it is present in the verified firmware.
- **Publish to an existing RTSP server:** use `rtspclientsink` only if that server accepts RTSP RECORD; element presence does not guarantee server support.
- **Host an RTSP server:** write a C/C++ server with `gst-rtsp-server-1.0`. The verified firmware has the 1.22.6 runtime library, while its production rootfs lacks headers and `.pc` files. Add matching compile-time metadata to the sysroot and link against the board-compatible target library.

The stock stream path is owned by `rkipc`, with `go2rtc` proxying it. Before integrating inference overlays, determine whether the application can consume the stock RTSP stream, whether metadata can travel out-of-band, or whether a separate encoded stream is required. Raw `/dev/video13` frames cannot be sent through `rtph264pay`; an actual H.264 encoder must precede `h264parse ! rtph264pay`. The verified GStreamer registry exposes no H.264 encoder, so use a firmware media API/stream, add a board-compatible encoder plugin, or encode outside GStreamer. Do not silently fall back to CPU encoding on this embedded target.

For a `gst-rtsp-server` media factory, payloaders must be named `pay0`, `pay1`, and so on. A typical already-encoded launch fragment is:

```text
( appsrc name=video_src is-live=true format=time ! video/x-h264,stream-format=byte-stream,alignment=au ! h264parse config-interval=-1 ! rtph264pay name=pay0 pt=96 )
```

This fragment assumes the application supplies valid timestamped H.264 access units. It does not encode raw inference frames.

## Sysroot and dependency inventory

Mirror target libraries while preserving symlinks, and obtain development headers and `.pc` metadata from the matching vendor SDK or a target-compatible development package. A live production rootfs commonly lacks headers and pkg-config files. Check both `/usr/lib` and `/usr/lib64`; the device plugin registry may report `/usr/lib64` even when symlinked files are visible under `/usr/lib`.

For every extra library, record:

```bash
file path/to/library.so
aarch64-linux-gnu-readelf -d path/to/library.so
aarch64-linux-gnu-readelf --version-info path/to/library.so
```

Compare GStreamer minor ABI, GLIBC requirements, SONAME, and every `DT_NEEDED` dependency with the board. A library merely existing in the local sysroot is not evidence that it exists on the board.
