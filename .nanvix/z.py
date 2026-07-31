# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

"""Nanvix build script for QuickJS.

Usage:
    ./z setup     # Download Nanvix sysroot
    ./z build     # Cross-compile qjs.elf, qjsc.elf, and libquickjs.a
    ./z test      # Run test suite (smoke + integration + functional)
    ./z release   # Package release tarball
    ./z clean     # Remove build artifacts
"""

import shutil
import sys
import tempfile
from pathlib import Path

from nanvix_zutil import (
    CFG_SYSROOT,
    DockerConfig,
    EXIT_MISSING_DEP,
    TOOLCHAIN_CONTAINER_PATH,
    ZScript,
    log,
    make_initrd,
    run,
    translate_path,
)
from nanvix_zutil.helpers import InitRdArgs
from nanvix_zutil.paths import (
    dev_out,
    dist_dir,
    nanvix_root,
    out_dir,
    regular_out,
    repo_root,
    test_out,
)

IS_WINDOWS = sys.platform == "win32"

# Makefile variable names (build-system-specific).
_MAKE_VAR_TOOLCHAIN = "NANVIX_TOOLCHAIN"
_MAKE_VAR_PLATFORM = "PLATFORM"
_MAKE_VAR_MEMORY_SIZE = "MEMORY_SIZE"

# Timeout for each nanvixd invocation (seconds).
_NANVIXD_TIMEOUT = 120

# Test JS files used in functional tests.
_FUNCTIONAL_TEST_FILES = [
    "tests/test_closure.js",
    "tests/test_language.js",
    "tests/test_builtin.js",
    "tests/test_loop.js",
    "tests/test_bigint.js",
    "tests/test_cyclic_import.js",
]

# Extra test files that require --std flag.
_FUNCTIONAL_TEST_FILES_STD = [
    "tests/test_builtin.js",
]

# Files that must be copied into the standalone ramfs.
_STANDALONE_RAMFS_SUPPORT_FILES = [
    "tests/assert.js",
    "tests/fixture_cyclic_import.js",
]


class QuickJSBuild(ZScript):
    """Build script for nanvix/quickjs."""

    # Build-time headers, libraries, startup objects, and linker scripts come
    # from the SDK. The downloaded sysroot is used only to run tests.
    SYSROOT_REQUIRED_FILES = (
        "bin/nanvixd.elf",
        "bin/kernel.elf",
        "bin/mkramfs.elf",
    )
    SYSROOT_REQUIRED_FILES_WINDOWS = (
        "bin/nanvixd.exe",
        "bin/kernel.elf",
        "bin/mkramfs.exe",
    )

    # Artifacts produced inside the Docker container that must be copied
    # back to the host workspace on Windows tar-copy mode (where the build
    # runs in a container-local directory instead of the mounted
    # workspace).  Two categories:
    #   * repo-root ELFs emitted by Makefile.nanvix;
    #   * install-staged paths under .nanvix/out/release/{bin,lib,include}
    #     required by `./z release` (see _staged_output_files()).
    _BUILD_OUTPUTS = [
        "qjs.elf",
        "qjsc.elf",
        "run-test262.elf",
    ]

    def _staged_output_files(self) -> list[str]:
        """Return install-staged artifact paths (relative to repo_root())
        so Windows tar-copy mode also copies them back to the host.
        """
        root = repo_root()
        return [
            str((regular_out() / "bin" / "qjs.elf").relative_to(root)),
            str((regular_out() / "bin" / "qjsc.elf").relative_to(root)),
            str((dev_out() / "lib" / "quickjs" / "libquickjs.a").relative_to(root)),
            str((dev_out() / "include" / "quickjs" / "quickjs.h").relative_to(root)),
            str(
                (dev_out() / "include" / "quickjs" / "quickjs-libc.h").relative_to(root)
            ),
        ]

    def docker_config(self, image: str) -> DockerConfig:
        cfg = super().docker_config(image)
        cfg.output_files = list(self._BUILD_OUTPUTS) + self._staged_output_files()
        return cfg

    def _make_args(self, *targets: str) -> list[str]:
        """Build the common make argument list."""
        toolchain_p = str(TOOLCHAIN_CONTAINER_PATH)

        def translate(p: Path):
            return translate_path(self.docker.mounts, p) if self.docker else p

        args = [
            "make",
            "-f",
            "Makefile.nanvix",
            f"{_MAKE_VAR_TOOLCHAIN}={toolchain_p}",
        ]

        args.extend(
            [
                f"{_MAKE_VAR_PLATFORM}={self.config.machine}",
                f"{_MAKE_VAR_MEMORY_SIZE}={self.config.memory_size}",
                f"NANVIX_ROOT={translate(nanvix_root())}",
                f"OUT_DIR={translate(out_dir())}",
                f"DIST_DIR={translate(dist_dir())}",
                f"LIB_OUT={translate(dev_out() / 'lib')}",
                f"INCLUDE_OUT={translate(dev_out() / 'include')}",
                f"BIN_OUT={translate(regular_out() / 'bin')}",
            ]
        )

        args.extend(targets)
        return args

    def _sysroot_path(self) -> Path:
        """Return the resolved sysroot path."""
        sysroot = self.config.get(CFG_SYSROOT, "")
        if not sysroot:
            log.fatal(
                f"{CFG_SYSROOT} is not set.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` first to download the sysroot.",
            )
        return Path(sysroot).resolve()

    def setup(self) -> bool:
        """Download the Nanvix sysroot."""
        return super().setup()

    def build(self) -> None:
        """Cross-compile qjs.elf, qjsc.elf, and libquickjs.a for Nanvix."""
        run(*self._make_args("all"), cwd=repo_root(), docker=self.docker)
        # Stage into test_out() for the windows-test upload glob
        # `.nanvix/out/test/**/*.{elf,so}` (workflows v2.3.0).
        test_out().mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root() / "qjs.elf", test_out() / "qjs.elf")

    def test(self) -> None:
        """Run the QuickJS functional test suite.

        Only the standalone deployment mode is supported. Initrd creation is
        handled in Python via make_initrd so that it is shared across
        platforms.
        """
        if IS_WINDOWS:
            self._run_tests_windows()
            return

        self._run_functional_standalone()

    # ------------------------------------------------------------------
    # Windows test implementation
    # ------------------------------------------------------------------

    def _run_tests_windows(self) -> None:
        """Run QuickJS functional tests natively on Windows."""
        self._run_functional_standalone()

        print("=== All QuickJS tests PASSED ===")

    def _run_functional_standalone(self) -> None:
        """Run standalone functional tests using make_initrd.

        Creates an initrd bundling qjs.elf with system daemons via
        make_initrd, and a ramfs providing test JS files.
        """
        # Prefer test_out() (windows-test overlay) over the Makefile's
        # repo-root output.
        qjs_elf_src: Path | None = None
        for candidate in (test_out() / "qjs.elf", repo_root() / "qjs.elf"):
            if candidate.is_file():
                qjs_elf_src = candidate
                break
        if qjs_elf_src is None:
            log.fatal(
                "qjs.elf not found.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z build` first.",
            )

        sysroot = self._sysroot_path()
        ext = ".exe" if IS_WINDOWS else ".elf"
        mkramfs = sysroot / "bin" / f"mkramfs{ext}"
        nanvixd = sysroot / "bin" / f"nanvixd{ext}"

        for tool in (mkramfs, nanvixd):
            if not tool.is_file():
                log.fatal(
                    f"{tool.name} not found at {tool}",
                    code=EXIT_MISSING_DEP,
                    hint="Run `./z setup` first.",
                )

        print("=== QuickJS functional tests ===")
        print("  Running tests via nanvixd standalone...")

        with tempfile.TemporaryDirectory(prefix="nanvix_quickjs_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            ramfs_dir = tmpdir_path / "ramfs"
            ramfs_tests = ramfs_dir / "tests"
            ramfs_tests.mkdir(parents=True)
            ramfs_img = tmpdir_path / "rootfs.img"

            # Copy test files + support files into the ramfs.
            for tf in _FUNCTIONAL_TEST_FILES + _STANDALONE_RAMFS_SUPPORT_FILES:
                shutil.copy2(repo_root() / tf, ramfs_tests / Path(tf).name)

            run(
                str(mkramfs),
                "-o",
                str(ramfs_img),
                str(ramfs_dir),
            )

            for tf in _FUNCTIONAL_TEST_FILES:
                guest_path = f"./tests/{Path(tf).name}"
                std_flag = tf in _FUNCTIONAL_TEST_FILES_STD
                app_args: list[str] = []
                if std_flag:
                    app_args.append("--std")
                app_args.append(guest_path)

                initrd = make_initrd(
                    qjs_elf_src,
                    test_out(),
                    args=InitRdArgs(app_args=app_args),
                )
                try:
                    run(
                        str(nanvixd),
                        "-bin-dir",
                        str(sysroot / "bin"),
                        "-ramfs",
                        str(ramfs_img),
                        "--",
                        str(initrd),
                        timeout=_NANVIXD_TIMEOUT,
                    )
                finally:
                    if initrd.exists():
                        initrd.unlink()

        print("  PASS: QuickJS functional tests")

    def clean(self) -> None:
        """Remove build artifacts."""
        run(
            "make",
            "-f",
            "Makefile.nanvix",
            "clean",
            cwd=repo_root(),
        )


if __name__ == "__main__":
    QuickJSBuild.main()
