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
import subprocess
import sys
import tempfile
from pathlib import Path

from nanvix_zutil import CFG_SYSROOT, CFG_TOOLCHAIN, EXIT_MISSING_DEP, ZScript, log

IS_WINDOWS = sys.platform == "win32"

# Makefile variable names (build-system-specific).
_MAKE_VAR_CONFIG = "CONFIG_NANVIX"
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

    def _make_args(self, *targets: str) -> list[str]:
        """Build the common make argument list."""
        sysroot = self.config.get(CFG_SYSROOT, "")
        if not sysroot:
            log.fatal(
                f"{CFG_SYSROOT} is not set.",
                code=EXIT_MISSING_DEP,
                hint="Run `./z setup` first to download the sysroot.",
            )
        toolchain = self.config.get(CFG_TOOLCHAIN, "/opt/nanvix")
        sysroot_p = self.translate_path(Path(sysroot))
        toolchain_p = self.translate_path(Path(toolchain))

        args = [
            "make",
            "-f",
            "Makefile.nanvix",
            f"{_MAKE_VAR_CONFIG}=y",
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
        self.run(*self._make_args("all"), cwd=self.repo_root)

    def test(self) -> None:
        """Run the QuickJS test suite.

        Without targets, runs the full suite (smoke + integration + functional).
        With targets (e.g. ``./z test -- test-smoke test-integration``), passes
        them directly to the Makefile.

        On Windows, runs the test suite natively using nanvixd.exe from
        the sysroot.
        """
        if IS_WINDOWS:
            targets = self.targets if self.targets else ["test"]
            self._run_tests_windows(targets)
            return
        targets = self.targets if self.targets else ["test"]
        self.run(*self._make_args(*targets), cwd=self.repo_root)

    # ------------------------------------------------------------------
    # Windows test implementation
    # ------------------------------------------------------------------

    def _run_tests_windows(self, targets: list[str]) -> None:
        """Run QuickJS tests natively on Windows.

        Mirrors the Makefile.nanvix test targets using nanvixd.exe and
        mkramfs.exe from the sysroot.
        """
        # Resolve which test phases to run, preserving Makefile dependency
        # semantics: test-functional implies test-integration implies
        # test-smoke.
        run_smoke = False
        run_integration = False
        run_functional = False

        for target in targets:
            if target in ("test", "test-functional"):
                run_smoke = run_integration = run_functional = True
            elif target == "test-integration":
                run_smoke = run_integration = True
            elif target == "test-smoke":
                run_smoke = True

        if run_smoke:
            self._win_test_smoke()
        if run_integration:
            self._win_test_integration()
        if run_functional:
            self._win_test_functional()

        print("=== All QuickJS tests PASSED ===")

    def _win_test_smoke(self) -> None:
        """Verify cross-compiled binaries exist and have reasonable sizes."""
        print("=== QuickJS smoke tests ===")
        # Only check binaries that are present in the test artifact.
        # libquickjs.a is a build-only output and not uploaded for tests.
        expected = [
            ("qjs.elf", 1000),
            ("qjsc.elf", 1000),
        ]
        for name, min_size in expected:
            path = self.repo_root / name
            if not path.is_file():
                log.fatal(
                    f"{name} not found at {path}",
                    code=EXIT_MISSING_DEP,
                    hint="Ensure the Linux build artifacts were downloaded.",
                )
            size = path.stat().st_size
            if size < min_size:
                log.fatal(f"{name} too small ({size} bytes)")
            print(f"  OK: {name} ({size} bytes)")

        for name in ("quickjs.h", "quickjs-libc.h"):
            path = self.repo_root / name
            if not path.is_file():
                log.fatal(f"{name} not found at {path}")
            print(f"  OK: {name}")

        print("  PASS: QuickJS smoke tests")

    def _win_test_integration(self) -> None:
        """Verify run-test262.elf exists."""
        print("=== QuickJS integration tests ===")
        path = self.repo_root / "run-test262.elf"
        if not path.is_file():
            log.fatal(
                f"run-test262.elf not found at {path}",
                code=EXIT_MISSING_DEP,
            )
        size = path.stat().st_size
        print(f"  OK: run-test262.elf ({size} bytes)")
        print("  PASS: QuickJS integration tests")

    def _win_test_functional(self) -> None:
        """Run functional tests using nanvixd.exe from the sysroot."""
        print("=== QuickJS functional tests ===")
        sysroot = self._sysroot_path()

        nanvixd = sysroot / "bin" / "nanvixd.exe"
        mkramfs = sysroot / "bin" / "mkramfs.exe"
        kernel = sysroot / "bin" / "kernel.elf"

        for tool in (nanvixd, mkramfs, kernel):
            if not tool.is_file():
                log.fatal(
                    f"{tool.name} not found at {tool}",
                    code=EXIT_MISSING_DEP,
                    hint="Run `./z setup` first.",
                )

        qjs = self.repo_root / "qjs.elf"
        if not qjs.is_file():
            log.fatal(f"qjs.elf not found at {qjs}")

        if self.config.deployment_mode == "standalone":
            self._win_functional_standalone(sysroot, nanvixd, mkramfs, qjs)
        else:
            self._win_functional_default(sysroot, nanvixd, qjs)

        print("  PASS: QuickJS functional tests")

    def _win_run_nanvixd(self, args: list[str], cwd: Path, label: str) -> None:
        """Run a single nanvixd invocation with timeout."""
        print(f"  RUN: {label}")
        log.info(f"$ {' '.join(args)}")
        try:
            subprocess.run(
                args,
                cwd=cwd,
                timeout=_NANVIXD_TIMEOUT,
                check=True,
            )
        except subprocess.TimeoutExpired:
            log.fatal(
                f"Timed out after {_NANVIXD_TIMEOUT}s: {label}",
            )
        except subprocess.CalledProcessError as exc:
            log.fatal(
                f"Failed with exit code {exc.returncode}: {label}",
            )

    def _win_functional_standalone(
        self,
        sysroot: Path,
        nanvixd: Path,
        mkramfs: Path,
        qjs: Path,
    ) -> None:
        """Run standalone functional tests with ramfs."""
        print("  Running tests via nanvixd.exe standalone...")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ramfs_dir = tmp / "nanvix-ramfs"
            ramfs_tests = ramfs_dir / "tests"
            ramfs_tests.mkdir(parents=True)
            rootfs_img = tmp / "rootfs.img"

            shutil.copy2(qjs, ramfs_dir / "qjs.elf")
            for tf in _FUNCTIONAL_TEST_FILES + _STANDALONE_RAMFS_SUPPORT_FILES:
                shutil.copy2(self.repo_root / tf, ramfs_tests / Path(tf).name)

            # Create ramfs image.
            log.info(f"$ {mkramfs} -o {rootfs_img} {ramfs_dir}/")
            subprocess.run(
                [str(mkramfs), "-o", str(rootfs_img), f"{ramfs_dir}/"],
                cwd=sysroot,
                check=True,
            )

            for tf in _FUNCTIONAL_TEST_FILES:
                guest_path = f"./tests/{Path(tf).name}"
                std_flag = tf in _FUNCTIONAL_TEST_FILES_STD
                cmd = [
                    str(nanvixd),
                    "-bin-dir",
                    "./bin",
                    "-ramfs",
                    str(rootfs_img),
                    "--",
                    str(qjs),
                ]
                if std_flag:
                    cmd.append("--std")
                cmd.append(guest_path)
                self._win_run_nanvixd(cmd, cwd=sysroot, label=guest_path)

    def _win_functional_default(
        self,
        sysroot: Path,
        nanvixd: Path,
        qjs: Path,
    ) -> None:
        """Run non-standalone functional tests."""
        print("  Running tests via nanvixd.exe...")
        all_tests = list(_FUNCTIONAL_TEST_FILES) + list(
            _FUNCTIONAL_EXTRA_NON_STANDALONE
        )

        std_files = set(_FUNCTIONAL_TEST_FILES_STD) | set(
            _FUNCTIONAL_EXTRA_NON_STANDALONE
        )

        for tf in all_tests:
            test_path = str(self.repo_root / tf)
            std_flag = tf in std_files
            cmd = [
                str(nanvixd),
                "--",
                str(qjs),
            ]
            if std_flag:
                cmd.append("--std")
            cmd.append(test_path)
            self._win_run_nanvixd(cmd, cwd=sysroot, label=tf)

    def release(self) -> None:
        """Package the QuickJS release tarball and verify it."""
        self.run(*self._make_args("package"), cwd=self.repo_root)
        self.run(*self._make_args("verify-package"), cwd=self.repo_root)

    def clean(self) -> None:
        """Remove build artifacts."""
        self.run(
            "make",
            "-f",
            "Makefile.nanvix",
            "clean",
            cwd=self.repo_root,
        )


if __name__ == "__main__":
    QuickJSBuild.main()
