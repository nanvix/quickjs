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
| **Nanvix Toolchain** | i686-nanvix cross-compiler | `/opt/nanvix` or `$HOME/toolchain` |
| **Nanvix Sysroot** | System libraries and linker script | `$HOME/nanvix` |

### Downloading the Latest Nanvix Release

Choose one of the methods below to download Nanvix.

#### Option 1: Using GitHub CLI (Recommended)

> **Prerequisite:** Install the [GitHub CLI](https://cli.github.com/) (`gh`)

```bash
# Step 1: Download the latest Nanvix microvm release
# Pattern matches: nanvix-microvm-single-process-*.tar.bz2
gh release download latest \
    --repo nanvix/nanvix \
    --pattern '*microvm*single*.tar.bz2'

# Step 2: Create a directory and extract the release
mkdir -p nanvix
tar -xjf nanvix-microvm-*.tar.bz2 -C nanvix --strip-components=1

# Step 3: Set the NANVIX_HOME environment variable
export NANVIX_HOME="$(pwd)/nanvix"

# Step 4: Verify the installation
echo "Nanvix installed at: $NANVIX_HOME"
ls -la "$NANVIX_HOME/bin/nanvixd.elf"
```

#### Option 2: Using curl and the GitHub API

> **Prerequisite:** You need `curl` and `jq` installed, plus a GitHub token.

```bash
# Step 1: Set your GitHub token for API authentication
# Create a token at: https://github.com/settings/tokens
export GH_TOKEN="your_github_token_here"

# Step 2: Query the GitHub API to find the download URL
RELEASE_API="https://api.github.com/repos/nanvix/nanvix/releases/tags/latest"
DOWNLOAD_URL=$(curl -fsSL -H "Authorization: Bearer ${GH_TOKEN}" "$RELEASE_API" | \
    jq -r '.assets[] | select(.name | test("microvm.*single.*\\.tar\\.bz2$")) | .browser_download_url' | \
    head -1)

# Step 3: Verify we found a valid URL
if [ -z "$DOWNLOAD_URL" ]; then
    echo "Error: Could not find Nanvix microvm artifact"
    exit 1
fi
echo "Downloading from: $DOWNLOAD_URL"

# Step 4: Download the release archive
curl -fsSL -H "Authorization: Bearer ${GH_TOKEN}" \
    "$DOWNLOAD_URL" \
    -o nanvix-release.tar.bz2

# Step 5: Extract the archive
mkdir -p nanvix
tar -xjf nanvix-release.tar.bz2 -C nanvix --strip-components=1

# Step 6: Set the NANVIX_HOME environment variable
export NANVIX_HOME="$(pwd)/nanvix"

# Step 7: Verify the installation
echo "Nanvix installed at: $NANVIX_HOME"
ls -la "$NANVIX_HOME/bin/nanvixd.elf"
```

---

## Building

### Method 1: Using the Makefile (Direct)

```bash
# Step 1: Set environment variables
export NANVIX_TOOLCHAIN=/path/to/toolchain  # Contains: bin/i686-nanvix-gcc
export NANVIX_HOME=/path/to/nanvix          # Contains: lib/user.ld, lib/libposix.a

# Step 2: Build all targets
make CONFIG_NANVIX=y all

# Step 3: (Optional) Check the build outputs
ls -la qjs.elf qjsc.elf libquickjs.a
```

### Method 2: Using the `z` Utility Script

The `z` utility provides a convenient wrapper with sensible defaults:

```bash
# Step 1: Configure paths (optional - uses defaults if skipped)
./z configure \
    --toolchain-path /path/to/toolchain \
    --sysroot-path /path/to/sysroot

# Step 2: Build
./z build

# Step 3: Install to sysroot (optional)
./z install

# Step 4: Clean build artifacts (when needed)
./z clean
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
# Step 1: Navigate to Nanvix home directory
cd "$NANVIX_HOME"

# Step 2: Run a test through the Nanvix daemon
./bin/nanvixd.elf -- /path/to/qjs.elf /path/to/test.js
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

---
