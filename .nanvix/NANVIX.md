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

# 2. Setup (uses the manifest SDK and downloads the Nanvix runtime)
./z setup

# 3. Build
./z build

# 4. Test
./z test

# 5. Package release tarballs
./z release
```

### Manual SDK Build

```bash
SDK="<immutable SDK reference from .nanvix/nanvix.toml>"
docker pull "$SDK"
docker run --rm --user "$(id -u):$(id -g)" \
    --volume "$PWD:/workspace" --workdir /workspace "$SDK" \
    make CONFIG_NANVIX=y NANVIX_TOOLCHAIN=/opt/nanvix
```

This builds target objects and links target executables with the SDK Clang
driver. Native `gcc` from the same image builds only host `qjsc` and generators.
Use the setup command from [Quick Start](#quick-start), then run `./z test` to
download the matching runtime and run tests.

---

## Prerequisites

You need the following components to build QuickJS for Nanvix:

| Component | Description | Default Location |
|-----------|-------------|------------------|
| **nanvix-zutil** | Build orchestration tool | `pip install nanvix-zutil` |
| **Nanvix C SDK** | Clang/LLVM, target libc, startup objects, and linker script | `/opt/nanvix` in the pinned image |
| **Nanvix Runtime** | Kernel, monitor, daemons, and image tools used by tests | `.nanvix/sysroot` |

> **Note:** `./z setup` downloads only the runtime. Build-time headers,
> libraries, startup objects, and linker scripts come from the SDK. The runtime
> version is declared in `.nanvix/nanvix.toml`.

### Available Platform Configurations

| Platform | Process Mode | Artifact Pattern |
|----------|--------------|------------------|
| microvm | standalone | `microvm.*standalone` |

Nanvix v0.20.0 publishes runtime artifacts only for microvm at 256 MiB; it has
no Hyperlight artifacts and no microvm standalone 128 MiB asset. The manifest
and active CI workflows therefore intentionally test every existing QuickJS
test type on microvm at 256 MiB only. Failure to resolve either unavailable
runtime configuration is a runtime compatibility limitation, not a QuickJS
port failure.

### Downloading the Nanvix Runtime

```bash
curl -fsSL https://raw.githubusercontent.com/nanvix/nanvix/refs/heads/dev/scripts/get-nanvix.sh | bash -s -- nanvix-artifacts
```

The script downloads release artifacts. Extract the standalone artifact
matching the target platform and memory size. `./z setup` performs this step
automatically for Nanvix runtime 0.20.0.

---

## Building

### Using nanvix-zutil (Recommended)

```bash
# Install nanvix-zutil
pip install nanvix-zutil

# Setup, build, and test in one go using the manifest SDK.
./z setup && ./z build && ./z test
```

The `./z` entry point automatically delegates to `z.sh` on Linux/macOS or `z.ps1` on
Windows, which in turn invokes the `nanvix-zutil` CLI. Build logic is defined in
`.nanvix/z.py`.

### Using Docker

The Makefile supports automatic Docker fallback when an installed SDK is not
available:

```bash
# Pull the immutable SDK reference declared in .nanvix/nanvix.toml.

# Build (Docker is used automatically if /opt/nanvix is not installed)
make CONFIG_NANVIX=y
```

The SDK Clang driver supplies the target sysroot, startup object, libc, libm,
compiler-rt, and linker script. No runtime libraries are linked from the
downloaded Nanvix runtime.

**Docker Fallback Behavior:**
- If `NANVIX_TOOLCHAIN` points to a valid SDK, it uses the installed SDK
- If the SDK is not found, it automatically uses Docker if available
- Use `CONFIG_NANVIX_DOCKER=y` to force Docker usage even when native toolchain exists
- `NANVIX_DOCKER_IMAGE` defaults to the digest-pinned SDK shown above

### Using an Installed SDK

```bash
export NANVIX_TOOLCHAIN=/path/to/nanvix-sdk # Contains: nanvix-sdk.json, bin/clang
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
| New Makefile | Added `Makefile.nanvix` for standardized Nanvix cross-compilation |
| nanvix-zutil integration | `.nanvix/z.py` ZScript subclass for build orchestration |
| Package manifest | `.nanvix/nanvix.toml` declares version and Nanvix dependency |
| Thin wrappers | `z.sh`, `z.ps1`, `z` entry points delegate to nanvix-zutil |
| AR tool | Fixed Makefile to conditionally set AR for Nanvix builds |
| SDK toolchain | Target objects and executable links use Clang/LLVM; host tools use host GCC |
| Runtime isolation | Downloaded Nanvix artifacts are runtime-only; the SDK owns target libc and linking |
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
| **No timezone support** | `getTimezoneOffset()` always returns 0 |
| **No shared libraries** | Cannot use `.so` dynamic modules |
| **Limited `os` module** | `os.exec()`, signals, and pipes unavailable |

---

## CI/CD

The GitHub Actions workflow at `.github/workflows/nanvix-ci.yml` is a thin caller that
invokes the reusable Nanvix CI workflow at
`nanvix/workflows/.github/workflows/nanvix-ci.yml@v2.5.0`.

### Trigger Events

| Event | Description |
|-------|-------------|
| Push to `nanvix/**` | Any push to Nanvix branches |
| PR to `nanvix/**` | Pull requests targeting Nanvix branches |
| Daily schedule | Runs at midnight UTC |
| Manual dispatch | Can be triggered manually |

### Build Matrix

The CI builds and tests the standalone deployment mode across platform configurations:

| Platform | Process Mode | Runner |
|----------|--------------|--------|
| microvm | standalone | `ubuntu-latest` (container) |

CI tests the runtime's 256 MiB memory configuration. All configurations run in
parallel with `fail-fast: false`.

---
