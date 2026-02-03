# QuickJS Port for Nanvix

> **TL;DR:** This is a port of the QuickJS JavaScript engine for the Nanvix operating system. Jump to [Quick Start](#quick-start) to get started immediately.

---

## Overview

This document describes the port of [QuickJS](https://bellard.org/quickjs/) JavaScript engine for the [Nanvix](https://github.com/nanvix/nanvix) operating system. This port enables QuickJS to run on Nanvix, a POSIX-compatible educational operating system.

| Property | Value |
|----------|-------|
| **Base Version** | QuickJS 2025-09-13 |
| **Base Commit** | `4af5b1e` (master) |
| **Target Platform** | Nanvix (i686) |
| **Build System** | GNU Make |

**What's included:**
- ✅ Cross-compilation support for Nanvix
- ✅ Platform-specific workarounds
- ✅ Nanvix-compatible test suite
- ✅ Build helper scripts
- ✅ CI/CD integration

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Building](#building)
4. [Testing](#testing)
5. [Changes Summary](#changes-summary)
6. [Known Limitations](#known-limitations)
7. [CI/CD](#cicd)

---

## Quick Start

For experienced users who want to build quickly:

```bash
# 1. Download Nanvix
gh release download latest --repo nanvix/nanvix --pattern '*microvm*single*.tar.bz2'
mkdir -p nanvix && tar -xjf nanvix-microvm-*.tar.bz2 -C nanvix --strip-components=1
export NANVIX_HOME="$(pwd)/nanvix"

# 2. Build QuickJS (assumes toolchain is at $HOME/toolchain)
make CONFIG_NANVIX=y NANVIX_TOOLCHAIN="$HOME/toolchain" all

# 3. Run tests
make CONFIG_NANVIX=y NANVIX_HOME="$NANVIX_HOME" test
```

Continue reading for detailed instructions.

---

## Prerequisites

You need two components to build QuickJS for Nanvix:

| Component | Description | Default Location |
|-----------|-------------|------------------|
| **Nanvix Toolchain** | i686-nanvix cross-compiler | `$HOME/toolchain` |
| **Nanvix Sysroot** | System libraries and linker script | `$HOME/nanvix` |

### Available Platform Configurations

Nanvix releases are available for multiple platform and process-mode combinations:

| Platform | Process Mode | Artifact Pattern |
|----------|--------------|------------------|
| hyperlight | multi-process | `*hyperlight*multi*.tar.bz2` |
| hyperlight | single-process | `*hyperlight*single*.tar.bz2` |
| microvm | single-process | `*microvm*single*.tar.bz2` |
| microvm | multi-process | `*microvm*multi*.tar.bz2` |

Choose the configuration that matches your target environment. The examples below use `microvm-single-process` but you can substitute any pattern.

### Downloading the Latest Nanvix Release

Choose one of the methods below to download Nanvix.

#### Option 1: Using GitHub CLI (Recommended)

> **Prerequisite:** Install the [GitHub CLI](https://cli.github.com/) (`gh`)

```bash
# Choose your platform pattern from the table above
PLATFORM_PATTERN='*microvm*single*.tar.bz2'

# Download and extract
gh release download latest --repo nanvix/nanvix --pattern "$PLATFORM_PATTERN"
mkdir -p nanvix && tar -xjf nanvix-*.tar.bz2 -C nanvix --strip-components=1
export NANVIX_HOME="$(pwd)/nanvix"
```

#### Option 2: Using curl and the GitHub API

> **Prerequisite:** `curl`, `jq`, and a [GitHub token](https://github.com/settings/tokens).

```bash
export GH_TOKEN="your_github_token_here"
PLATFORM_PATTERN="microvm.*single-process"  # See table above for options

# Fetch download URL and download
API_URL="https://api.github.com/repos/nanvix/nanvix/releases/tags/latest"
DOWNLOAD_URL=$(curl -fsSL -H "Authorization: Bearer ${GH_TOKEN}" "$API_URL" | \
    jq -r --arg p "$PLATFORM_PATTERN" '.assets[] | select(.name | test($p)) | .browser_download_url' | head -1)
curl -fsSL -H "Authorization: Bearer ${GH_TOKEN}" "$DOWNLOAD_URL" -o nanvix-release.tar.bz2

# Extract and set environment
mkdir -p nanvix && tar -xjf nanvix-release.tar.bz2 -C nanvix --strip-components=1
export NANVIX_HOME="$(pwd)/nanvix"
```

---

## Building

### Method 1: Using the Makefile (Direct)

```bash
export NANVIX_TOOLCHAIN=/path/to/toolchain  # Contains: bin/i686-nanvix-gcc
export NANVIX_HOME=/path/to/nanvix          # Contains: lib/user.ld, lib/libposix.a
make CONFIG_NANVIX=y all
```

### Method 2: Using the `z` Utility Script

The `z` utility provides a convenient wrapper with sensible defaults:

```bash
./z configure --toolchain-path /path/to/toolchain --sysroot-path /path/to/sysroot
./z build
./z install  # Optional: install to sysroot
./z clean    # Optional: clean build artifacts
```

### Build Outputs

After a successful build, you will have:

| File | Description |
|------|-------------|
| `qjs.elf` | QuickJS interpreter executable |
| `qjsc.elf` | QuickJS compiler executable |
| `run-test262.elf` | ECMAScript test suite runner |
| `libquickjs.a` | QuickJS static library |

---

## Testing

> **Important:** Tests must be run through the Nanvix daemon (`nanvixd.elf`).

### Running the Full Test Suite

```bash
# Run all tests
make CONFIG_NANVIX=y NANVIX_HOME=/path/to/nanvix test
```

### Running Microbenchmarks

```bash
# Run performance benchmarks
make CONFIG_NANVIX=y NANVIX_HOME=/path/to/nanvix microbench
```

### Running Individual Tests

To run a single test file manually:

```bash
cd "$NANVIX_HOME" && ./bin/nanvixd.elf -- /path/to/qjs.elf /path/to/test.js
```

### Available Test Files

| Test File | Description |
|-----------|-------------|
| `test_closure.js` | Closure functionality tests |
| `test_language.js` | JavaScript language feature tests |
| `test_builtin.js` | Built-in object tests |
| `test_loop.js` | Loop construct tests |
| `test_bigint.js` | BigInt support tests |
| `test_cyclic_import.js` | Cyclic module import tests |
| `test_worker.js` | Worker thread tests |
| `test_std_nanvix.js` | Nanvix-compatible standard library tests |

---

## Changes Summary

The following changes were made on top of commit `4af5b1e` (master branch) to support Nanvix.

### Build System Changes

| Change | Description |
|--------|-------------|
| Cross-compilation | Added `CONFIG_NANVIX=y` option to enable Nanvix build |
| AR tool | Fixed Makefile to conditionally set AR for Nanvix builds |
| Linker flags | Added Nanvix-specific flags (`-T user.ld -static`) |
| Shared libraries | Disabled (not supported on Nanvix) |
| Test target | Modified to run via `nanvixd.elf` |

### Source Code Changes

#### File: `quickjs.c`
- Workaround for broken `inttypes.h` header (include `<sys/_stdint.h>` first)
- Added `__nanvix__` platform detection for `malloc.h` and `malloc_usable_size()`
- Timezone workaround (returns 0 offset; `tm_gmtoff` unavailable)

#### File: `quickjs-libc.c`
- Added `__nanvix__` detection for `get_time_ms()` function
- Set `OS_PLATFORM` to `"nanvix"`

#### File: `qjs.c`
- Added `__nanvix__` detection for malloc headers and `malloc_usable_size()`

### New Files

| File | Purpose |
|------|---------|
| `tests/test_std_nanvix.js` | Nanvix-compatible std library tests |
| `z` | Build helper script |
| `.github/workflows/nanvix-ci.yml` | CI workflow for automated builds |

---

## Known Limitations

| Limitation | Impact |
|------------|--------|
| **No timezone support** | `getTimezoneOffset()` always returns 0 |
| **No shared libraries** | Cannot use `.so` dynamic modules |
| **Limited `os` module** | `os.exec()`, signals, and pipes unavailable |

---

## CI/CD

The GitHub Actions workflow at `.github/workflows/nanvix-ci.yml` automates building and testing on every change.

### Trigger Events

| Event | Description |
|-------|-------------|
| Push to `nanvix/**` | Any push to Nanvix branches |
| PR to `nanvix/**` | Pull requests targeting Nanvix branches |
| Daily schedule | Runs at midnight UTC |
| Manual dispatch | Can be triggered manually |
| Repository dispatch | Triggered by `nanvix-release` events |

### Build Matrix

The CI runs on 4 different platform/process-mode configurations, each on a dedicated self-hosted runner:

| Platform | Process Mode | Runner |
|----------|--------------|--------|
| hyperlight | multi-process | `self-hosted-hyperlight-multi` |
| hyperlight | single-process | `self-hosted-hyperlight-single` |
| microvm | single-process | `self-hosted-microvm-single` |
| microvm | multi-process | `self-hosted-microvm-multi` |

All configurations run in parallel with `fail-fast: false`, ensuring that all platforms are tested even if one fails.

---
