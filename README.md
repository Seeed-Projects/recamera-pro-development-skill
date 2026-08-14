# Seeed reCamera Pro Development Skill for Gemini CLI

[中文说明](README-cn.md)

<p align="center">
  <img src="./assets/images/recamera_skill.png" alt="reCamera Pro Skills — natural-language development workflow" width="100%">
</p>

Develop applications for Seeed reCamera Pro through natural-language conversations with Gemini CLI.

After installing this skill, you can describe what you want to build—such as an AI camera application, an ONNX model conversion, microphone capture, speaker playback, or an RTSP inference stream—and Gemini CLI will use the reCamera Pro-specific workflow, tools, and hardware knowledge included in this repository.

## Choose your agent branch

Clone the branch for the agent you use. Each branch contains the same reCamera Pro development workflow with agent-specific installation and usage instructions.

| Agent | Branch | User skill directory |
| --- | --- | --- |
| OpenAI Codex | `main` | `~/.agents/skills/recamera-rknn-dev` |
| Claude Code | `claude-code` | `~/.claude/skills/recamera-rknn-dev` |
| GitHub Copilot | `github-copilot` | `~/.copilot/skills/recamera-rknn-dev` |
| Cursor | `cursor` | `~/.cursor/skills/recamera-rknn-dev` |
| Gemini CLI | `gemini-cli` | `~/.gemini/skills/recamera-rknn-dev` |

This `gemini-cli` branch is the Gemini CLI edition.

## What you can ask Gemini CLI to do

### Convert AI models

Ask Gemini CLI to convert an ONNX model into an RKNN model for the RV1126B NPU. The skill keeps RKNN-Toolkit2 and RKNN Runtime aligned at version 2.3.2, inspects the model contract, handles FP16 or INT8 conversion, and preserves conversion metadata.

Example:

> Use the reCamera Pro skill to convert my `model.onnx` into an RKNN model for RV1126B.

### Build native AI applications

Ask Gemini CLI to create or modify C/C++ applications that use the RKNN Runtime on reCamera Pro. The skill understands the aarch64 target, cross-compilation requirements, sysroot layout, runtime library path, ABI checks, and deployment constraints.

Example:

> Build a reCamera Pro application that captures camera frames and runs my RKNN object-detection model.

### Use the camera, microphone, and speaker

The skill contains verified information about the reCamera Pro camera node, ALSA audio device, microphone capture, speaker playback, media-device conflicts, and supported formats.

Example:

> Add microphone recording and speaker playback to my reCamera Pro application.

### Develop GStreamer and RTSP pipelines

Ask Gemini CLI to inspect the available GStreamer plugins, prepare cross-compilation dependencies, consume or publish RTSP streams, and integrate inference results into a multimedia application.

Example:

> Create an RTSP inference application for reCamera Pro and explain which dependencies need to be cross-compiled.

### Diagnose the development environment

Gemini CLI can inspect the host, toolchain, sysroot, target libraries, camera and audio devices, GStreamer plugins, ELF dependencies, and RKNN version compatibility before building.

Example:

> Check whether my computer is ready to cross-compile applications for reCamera Pro and fix the missing development dependencies.

## Supported platform

This skill is designed specifically for:

- Seeed reCamera Pro
- Rockchip RV1126B
- aarch64 Linux
- RKNN-Toolkit2 2.3.2
- RKNN Runtime 2.3.2

It is not intended for the SG2002/riscv64 reCamera platform.

## Install

### Ask Gemini CLI to install it

Send Gemini CLI this request:

```text
Install the reCamera Pro development skill from:
https://github.com/Seeed-Projects/recamera-pro-development-skill.git
```

### Install manually

```bash
git clone --branch gemini-cli --single-branch https://github.com/Seeed-Projects/recamera-pro-development-skill.git
cd recamera-pro-development-skill
./scripts/install_skill.sh
```

The skill is installed as:

```text
~/.gemini/skills/recamera-rknn-dev
```

Run `/skills reload` in Gemini CLI after installation, then confirm it with `/skills list`.

## Use

You can mention the skill explicitly:

> Use `recamera-rknn-dev` to build an application for reCamera Pro that detects people and publishes the annotated video over RTSP.

You can also describe the task naturally after the skill is installed:

> I have an ONNX detection model. Convert it for reCamera Pro and create the corresponding C++ camera application.

Gemini CLI will load the relevant conversion, cross-compilation, camera, audio, or streaming guidance automatically. Device connections, file transfers, and on-device execution are performed only when you explicitly request and authorize them.

## Included knowledge

The repository packages reusable Gemini CLI instructions, scripts, references, a native application template, and the Seeed-qualified RKNN Runtime 2.3.2 cross-link library. The technical commands are intentionally kept inside the skill so users can work primarily through natural language.

Before public release, the repository owner must add the applicable project license and any required notices for redistributed binary components.
