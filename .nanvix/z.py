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
)
from nanvix_zutil.helpers import InitRdArgs

IS_WINDOWS = sys.platform == "win32"

# Makefile variable names (build-system-specific).
_MAKE_VAR_HOME = "NANVIX_HOME"
_MAKE_VAR_TOOLCHAIN = "NANVIX_TOOLCHAIN"
_MAKE_VAR_PLATFORM = "PLATFORM"
_MAKE_VAR_PROCESS_MODE = "PROCESS_MODE"
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

# Additional test files for non-standalone modes.
_FUNCTIONAL_EXTRA_NON_STANDALONE = [
    "tests/test_worker.js",
    "tests/test_std_nanvix.js",
]

# Files that must be copied into the standalone ramfs.
_STANDALONE_RAMFS_SUPPORT_FILES = [
    "tests/assert.js",
    "tests/fixture_cyclic_import.js",
]


class QuickJSBuild(ZScript):
    """Build script for nanvix/quickjs."""

    # Build artifacts produced by `make all` that must be copied back from
    # the container-local build directory to the host workspace on Windows
    # (where `build_windows_run_cmd` uses tar-based source copying).
    _BUILD_OUTPUTS = [
        "qjs.elf",
        "qjsc.elf",
        "run-test262.elf",
        "libquickjs.a",
    ]

    def docker_config(self, image: str) -> DockerConfig:
        cfg = super().docker_config(image)
        cfg.output_files = list(self._BUILD_OUTPUTS)
        return cfg

    def _make_args(self, *targets: str) -> list[str]:
        """Build the common make argument list."""
        sysroot = self.config.get(CFG_SYSROOT, "")
        if not sysroot:
            log.fatal(
                f"{CFG_SYSROOT} is not set.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` first to download the sysroot.",
            )
        toolchain_p = str(TOOLCHAIN_CONTAINER_PATH)
        sysroot_p = (
            self.docker.translate_path(Path(sysroot)) if self.docker else Path(sysroot)
        )

        args = [
            "make",
            "-f",
            "Makefile.nanvix",
            f"{_MAKE_VAR_HOME}={sysroot_p}",
            f"{_MAKE_VAR_TOOLCHAIN}={toolchain_p}",
        ]

        args.extend(
            [
                f"{_MAKE_VAR_PLATFORM}={self.config.machine}",
                f"{_MAKE_VAR_PROCESS_MODE}={self.config.deployment_mode}",
                f"{_MAKE_VAR_MEMORY_SIZE}={self.config.memory_size}",
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
        run(*self._make_args("all"), cwd=self.repo_root, docker=self.docker)

    def test(self) -> None:
        """Run the QuickJS functional test suite.

        Standalone mode is handled in Python via make_initrd so that initrd
        creation is shared across platforms. Non-standalone mode delegates
        to the Makefile, which runs the functional tests via nanvixd.
        """
        if IS_WINDOWS:
            self._run_tests_windows()
            return

        if self.config.deployment_mode == "standalone":
            self._run_functional_standalone()
        else:
            targets = self.targets if self.targets else ["test"]
            run(
                *self._make_args(*targets),
                cwd=self.repo_root,
            )

    # ------------------------------------------------------------------
    # Windows test implementation
    # ------------------------------------------------------------------

    def _run_tests_windows(self) -> None:
        """Run QuickJS functional tests natively on Windows."""
        if self.config.deployment_mode == "standalone":
            self._run_functional_standalone()
        else:
            self._run_functional_non_standalone()

        print("=== All QuickJS tests PASSED ===")

    def _run_functional_standalone(self) -> None:
        """Run standalone functional tests using make_initrd.

        Creates an initrd bundling qjs.elf with system daemons via
        make_initrd, and a ramfs providing test JS files.
        """
        qjs_elf = self.repo_root / "qjs.elf"
        if not qjs_elf.is_file():
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
                shutil.copy2(self.repo_root / tf, ramfs_tests / Path(tf).name)

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

                initrd = make_initrd(self, "qjs.elf", InitRdArgs(app_args=app_args))
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

    def _run_functional_non_standalone(self) -> None:
        """Run non-standalone functional tests.

        Uses nanvixd directly with the qjs.elf path and a ramfs
        providing /tmp for any test I/O.
        """
        qjs_elf = self.repo_root / "qjs.elf"
        if not qjs_elf.is_file():
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

        all_tests = list(_FUNCTIONAL_TEST_FILES) + list(
            _FUNCTIONAL_EXTRA_NON_STANDALONE
        )
        std_files = set(_FUNCTIONAL_TEST_FILES_STD) | set(
            _FUNCTIONAL_EXTRA_NON_STANDALONE
        )

        print("=== QuickJS functional tests ===")
        print("  Running tests via nanvixd...")

        with tempfile.TemporaryDirectory(prefix="nanvix_quickjs_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            ramfs_dir = tmpdir_path / "ramfs"
            ramfs_dir.mkdir()
            (ramfs_dir / "tmp").mkdir()
            ramfs_img = tmpdir_path / "rootfs.img"

            run(
                str(mkramfs),
                "-o",
                str(ramfs_img),
                str(ramfs_dir),
            )

            for tf in all_tests:
                test_path = str((self.repo_root / tf).resolve())
                std_flag = tf in std_files
                cmd: list[str] = [
                    str(nanvixd),
                    "-bin-dir",
                    str(sysroot / "bin"),
                    "-ramfs",
                    str(ramfs_img),
                    "--",
                    str(qjs_elf.resolve()),
                ]
                if std_flag:
                    cmd.append("--std")
                cmd.append(test_path)
                run(*cmd, timeout=_NANVIXD_TIMEOUT)

        print("  PASS: QuickJS functional tests")

    def release(self) -> None:
        """Package the QuickJS release tarball and verify it."""
        for artifact in ("qjs.elf", "qjsc.elf", "libquickjs.a"):
            if not (self.repo_root / artifact).is_file():
                log.fatal(
                    f"{artifact} not found.",
                    code=EXIT_MISSING_DEP,
                    hint="Run `./z build` first.",
                )
        run(*self._make_args("package"), cwd=self.repo_root)
        run(*self._make_args("verify-package"), cwd=self.repo_root)

    def clean(self) -> None:
        """Remove build artifacts."""
        run(
            "make",
            "-f",
            "Makefile.nanvix",
            "clean",
            cwd=self.repo_root,
        )


if __name__ == "__main__":
    QuickJSBuild.main()
