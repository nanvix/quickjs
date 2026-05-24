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
    TOOLCHAIN_CONTAINER_PATH,
    EXIT_MISSING_DEP,
    ZScript,
    log,
)

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
        toolchain = str(TOOLCHAIN_CONTAINER_PATH)
        sysroot_p = self.translate_path(Path(sysroot))
        toolchain_p = toolchain

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

        Smoke and integration tests are always delegated to the Makefile.
        The functional test in standalone mode is handled in Python via
        make_initrd so that initrd creation is shared across platforms.
        """
        if IS_WINDOWS:
            targets = self.targets if self.targets else ["test"]
            self._run_tests_windows(targets)
            return

        if self.config.deployment_mode == "standalone":
            targets = self.targets if self.targets else []
            _functional_targets = {"test", "test-functional"}
            needs_functional = not targets or bool(set(targets) & _functional_targets)
            make_targets = [t for t in targets if t not in _functional_targets]
            if not targets or "test" in targets:
                # Full suite or umbrella "test": run all prerequisites.
                make_targets = ["test-smoke", "test-integration"]
            elif needs_functional and make_targets:
                # Functional requested alongside other explicit targets:
                # ensure the prerequisite chain is complete.
                if "test-integration" not in make_targets:
                    make_targets.append("test-integration")
                if "test-smoke" not in make_targets:
                    make_targets.insert(0, "test-smoke")
            # When only "test-functional" is requested (e.g. delegated
            # from the Makefile which already ran prerequisites), skip
            # Make targets to avoid double-execution.
            if make_targets:
                self.run(*self._make_args(*make_targets), cwd=self.repo_root)
            if needs_functional:
                self._run_functional_standalone()
        else:
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
            if self.config.deployment_mode == "standalone":
                self._run_functional_standalone()
            else:
                self._run_functional_non_standalone()

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

            self.run(
                str(mkramfs),
                "-o",
                str(ramfs_img),
                str(ramfs_dir),
                docker=False,
            )

            for tf in _FUNCTIONAL_TEST_FILES:
                guest_path = f"./tests/{Path(tf).name}"
                std_flag = tf in _FUNCTIONAL_TEST_FILES_STD
                app_args: list[str] = []
                if std_flag:
                    app_args.append("--std")
                app_args.append(guest_path)

                initrd = self.make_initrd("qjs.elf", app_args=app_args)
                try:
                    self.run(
                        str(nanvixd),
                        "-bin-dir",
                        str(sysroot / "bin"),
                        "-ramfs",
                        str(ramfs_img),
                        "--",
                        str(initrd),
                        docker=False,
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

            self.run(
                str(mkramfs),
                "-o",
                str(ramfs_img),
                str(ramfs_dir),
                docker=False,
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
                self.run(*cmd, docker=False, timeout=_NANVIXD_TIMEOUT)

        print("  PASS: QuickJS functional tests")

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
