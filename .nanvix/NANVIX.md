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
| **Toolchain** | Nanvix LLVM — `clang` (target `i686-unknown-nanvix`) + `llvm-ar` |
| **Docker Image** | `ghcr.io/nanvix/llvm-project:ca7933e47d3a` |
| **Build Orchestration** | [nanvix-zutil](https://github.com/nanvix/zutils) |

**What's included:**
- ✅ Cross-compilation support for Nanvix
- ✅ Platform-specific workarounds
- ✅ Nanvix-compatible test suite
- ✅ nanvix-zutil integration (`z.sh` / `z.ps1` / `.nanvix/z.py`)
- ✅ CI/CD integration via reusable workflow

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

For experienced users who want to build quickly using nanvix-zutil:

```bash
# 1. Install nanvix-zutil
pip install nanvix-zutil

# 2. Setup (downloads Nanvix sysroot automatically)
./z setup

# 3. Build
./z build

# 4. Test
./z test

# 5. Package release tarballs
./z release
```

### Manual Build (without nanvix-zutil)

```bash
# 1. Pull the Docker image (Nanvix LLVM toolchain)
docker pull ghcr.io/nanvix/llvm-project:ca7933e47d3a

# 2. Download Nanvix sysroot
curl -fsSL https://raw.githubusercontent.com/nanvix/nanvix/refs/heads/dev/scripts/get-nanvix.sh | bash -s -- nanvix-artifacts
tar -xjf nanvix-artifacts/*microvm*single*.tar.bz2 -C nanvix-artifacts
export NANVIX_HOME=$(find nanvix-artifacts -maxdepth 2 -type d -name "bin" -exec dirname {} \; | head -1)

# 3. Build (Docker is used automatically if native toolchain is not found)
make CONFIG_NANVIX=y NANVIX_HOME="$NANVIX_HOME"

# 4. Run tests
make CONFIG_NANVIX=y NANVIX_HOME="$NANVIX_HOME" test
```

Continue reading for detailed instructions.

---

## Prerequisites

You need the following components to build QuickJS for Nanvix:

| Component | Description | Default Location |
|-----------|-------------|------------------|
| **nanvix-zutil** | Build orchestration tool | `pip install nanvix-zutil` |
| **Nanvix LLVM Toolchain** | `clang`/`llvm-ar` cross-compiler + bundled sysroot | `/opt/nanvix` (in Docker image) |
| **Nanvix Runtime Sysroot** | `nanvixd.elf` + daemons, used to run tests | `$HOME/nanvix` |

> **Note:** When using nanvix-zutil (`./z setup`), the sysroot is downloaded
> automatically. The Nanvix version is declared in `.nanvix/nanvix.toml`.

### Available Platform Configurations

> **Note:** This port supports **only the `standalone` deployment mode.** The
> multi-process and single-process modes are not supported (QuickJS runs as a
> single guest without a Linux personality; `os.Worker`/threads are unavailable).

| Platform | Process Mode | Artifact Pattern |
|----------|--------------|------------------|
| hyperlight | standalone | `hyperlight.*standalone` |
| microvm | standalone | `microvm.*standalone` |

### Downloading Nanvix

```bash
curl -fsSL https://raw.githubusercontent.com/nanvix/nanvix/refs/heads/dev/scripts/get-nanvix.sh | bash -s -- nanvix-artifacts
```

The script downloads all release artifacts. Extract the one matching your target platform (see [Quick Start](#quick-start) for a complete example).

---

## Building

### Using nanvix-zutil (Recommended)

```bash
# Install nanvix-zutil
pip install nanvix-zutil

# Setup, build, and test in one go
./z setup && ./z build && ./z test
```

The `./z` entry point automatically delegates to `z.sh` on Linux/macOS or `z.ps1` on
Windows, which in turn invokes the `nanvix-zutil` CLI. Build logic is defined in
`.nanvix/z.py`.

### Using Docker

The Makefile supports automatic Docker fallback when the native toolchain is not available:

```bash
# Pull the Nanvix LLVM toolchain Docker image
docker pull ghcr.io/nanvix/llvm-project:ca7933e47d3a

# Build (Docker is used automatically if native toolchain is not found)
make CONFIG_NANVIX=y NANVIX_HOME=/path/to/nanvix/sysroot-debug
```

> **Note:** The toolchain image is self-contained: `clang` targets
> `i686-unknown-nanvix` and resolves system headers, the startup object
> (`crt0.o`), the C/math libraries, and compiler-rt from its bundled sysroot at
> `/opt/nanvix`. `NANVIX_HOME` is only the **runtime** sysroot (provides
> `bin/nanvixd.elf` and daemons) used by `test`.

**Docker Fallback Behavior:**
- If `NANVIX_TOOLCHAIN` points to a valid toolchain (containing `bin/clang`), it uses the native compiler
- If the native toolchain is not found, it automatically uses Docker if available
- Use `CONFIG_NANVIX_DOCKER=y` to force Docker usage even when native toolchain exists
- Use `NANVIX_DOCKER_IMAGE` to specify a custom Docker image (default: `ghcr.io/nanvix/llvm-project:ca7933e47d3a`)

### Using Native Toolchain

```bash
export NANVIX_TOOLCHAIN=/path/to/toolchain  # Contains: bin/clang, bin/llvm-ar, lib/user.ld, and the sysroot
export NANVIX_HOME=/path/to/nanvix          # Runtime sysroot: contains bin/nanvixd.elf (used by `test`)
make CONFIG_NANVIX=y all
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
# Using nanvix-zutil
./z test

# Or directly via Make
make -f Makefile.nanvix CONFIG_NANVIX=y NANVIX_HOME=/path/to/nanvix test

# Or via the original Makefile
make CONFIG_NANVIX=y NANVIX_HOME=/path/to/nanvix test
```

### Running Microbenchmarks

```bash
# Via the original Makefile
make CONFIG_NANVIX=y NANVIX_HOME=/path/to/nanvix microbench
```

### Running Individual Tests

The functional suite runs in **standalone** mode: `./z test` bundles `qjs.elf`
with the system daemons (`procd`/`memd`/`vfsd`) into an initrd and runs it under
`nanvixd` with a ramfs containing the test scripts. To iterate on a single test,
edit the `_FUNCTIONAL_TEST_FILES` list in `.nanvix/z.py` and re-run:

```bash
./z test
```

### Available Test Files

The standalone functional suite runs the following (see `_FUNCTIONAL_TEST_FILES`
in `.nanvix/z.py`):

| Test File | Description |
|-----------|-------------|
| `test_closure.js` | Closure functionality tests |
| `test_language.js` | JavaScript language feature tests |
| `test_builtin.js` | Built-in object tests (`--std`) |
| `test_loop.js` | Loop construct tests |
| `test_bigint.js` | BigInt support tests |
| `test_cyclic_import.js` | Cyclic module import tests |
| `test_std_nanvix.js` | Nanvix-compatible standard library tests (`--std`) |

> `tests/test_worker.js` (Worker threads) is **not** run: threads require a
> multi-process deployment, which this port does not support.

---

## Changes Summary

The following changes were made on top of commit `4af5b1e` (master branch) to support Nanvix.

### Build System Changes

| Change | Description |
|--------|-------------|
| Cross-compilation | Added `CONFIG_NANVIX=y` option to enable Nanvix build |
| LLVM toolchain | `clang` (compile + link driver) + `llvm-ar`; image `ghcr.io/nanvix/llvm-project` |
| Compile flags | `--target=i686-unknown-nanvix` (sysroot headers auto-resolved; `__nanvix__` predefined) |
| Link flags | clang driver: `--target=i686-unknown-nanvix -T <toolchain>/lib/user.ld -Wl,--entry=_do_start -Wl,--allow-multiple-definition -Wl,-z,noexecstack` |
| Link libraries | `crt0.o`, `libc.a`, `libm.a`, compiler-rt auto-linked from the toolchain sysroot (POSIX merged into `libc.a`) |
| New Makefile | Added `Makefile.nanvix` for standardized Nanvix cross-compilation |
| nanvix-zutil integration | `.nanvix/z.py` ZScript subclass for build orchestration |
| Package manifest | `.nanvix/nanvix.toml` declares version and Nanvix dependency |
| Thin wrappers | `z.sh`, `z.ps1`, `z` entry points delegate to nanvix-zutil |
| Shared libraries | Disabled (not supported on Nanvix) |
| Test target | Modified to run via `nanvixd.elf` |
| Package targets | `package` and `verify-package` for release tarball creation |

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

### Nanvix-Specific Files

| File | Purpose |
|------|---------|
| `Makefile.nanvix` | Standalone Makefile for Nanvix cross-compilation |
| `NANVIX.md` | This documentation file |
| `.nanvix/z.py` | ZScript subclass (build orchestration logic) |
| `.nanvix/nanvix.toml` | Package manifest with Nanvix version declaration |
| `z` | Cross-platform entry point (routes to z.sh or z.ps1) |
| `z.sh` | Thin bash wrapper for nanvix-zutil |
| `z.ps1` | Thin PowerShell wrapper for nanvix-zutil |
| `.github/workflows/nanvix-ci.yml` | CI workflow (thin caller to reusable workflow) |

---

## Known Limitations

| Limitation | Impact |
|------------|--------|
| **Standalone only** | Only the `standalone` deployment mode is supported (no multi-process / single-process) |
| **No threads / workers** | `os.Worker` is unavailable (threads require a multi-process deployment) |
| **No timezone support** | `getTimezoneOffset()` always returns 0 |
| **No shared libraries** | Cannot use `.so` dynamic modules |
| **Limited `os` module** | `os.exec()`, signals, and pipes unavailable |

---

## CI/CD

The GitHub Actions workflow at `.github/workflows/nanvix-ci.yml` is a thin caller that
invokes the reusable Nanvix CI workflow at
`nanvix/workflows/.github/workflows/nanvix-ci.yml@v1.0.0`.

### Trigger Events

| Event | Description |
|-------|-------------|
| Push to `nanvix/**` | Any push to Nanvix branches |
| PR to `nanvix/**` | Pull requests targeting Nanvix branches |
| Daily schedule | Runs at midnight UTC |
| Manual dispatch | Can be triggered manually |

### Build Matrix

The CI runs the `standalone` deployment mode across platform/memory
configurations (multi-process and single-process are not supported):

| Platform | Process Mode | Runner |
|----------|--------------|--------|
| microvm | standalone | `ubuntu-latest` (container) |

All configurations run in parallel with `fail-fast: false`.

---
