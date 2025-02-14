#  Copyright  2021 Alexis Lopez Zubieta
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.

import logging
import random
import shutil
import string
from pathlib import Path
from typing import Final

from appimagebuilder.utils import elf, file_utils
from appimagebuilder.utils.finder import Finder
from . import helpers
from .apprun_binaries_resolver import AppRunBinariesResolver
from .environment import Environment
from .executables import BinaryExecutable, InterpretedExecutable
from .executables_patcher import ExecutablesPatcher
from .executables_scanner import ExecutablesScanner


class RuntimeGeneratorError(RuntimeError):
    pass


class RuntimeGenerator:
    def __init__(self, recipe: {}, finder: Finder):
        self.appdir_path = Path(recipe.AppDir.path()).absolute()
        self.main_exec = recipe.AppDir.app_info.exec()
        self.main_exec_args = recipe.AppDir.app_info.exec_args() or "$@"
        self.apprun_version = recipe.AppDir.runtime.version() or "continuous"
        self.apprun_debug = recipe.AppDir.runtime.debug()
        user_env_input = recipe.AppDir.runtime.env() or {}
        self.user_env = self.parse_env_input(user_env_input)

        self.default_runtime_path = self.appdir_path / "runtime" / "default"
        self.compat_runtime_path = self.appdir_path / "runtime" / "compat"

        self.deploy_hooks = not recipe.AppDir.runtime.no_hooks()
        if not self.deploy_hooks:
            logging.warning("Runtime hooks will not be deployed")

        self.path_mappings = recipe.AppDir.runtime.path_mappings()
        if self.path_mappings and not self.deploy_hooks:
            logging.error("Hooks required when setting path mappings")
            raise RuntimeError("Path Mappings set without hooks")

        self.preserve_paths = recipe.AppDir.runtime.preserve() or []

        self.finder = finder

        self.path_mappings_env: Final = "APPDIR_PATH_MAPPINGS"

    def generate(self):
        runtime_env = self._configure_runtime_environment()

        scanner = ExecutablesScanner(self.appdir_path, self.finder)
        resolver = AppRunBinariesResolver(self.apprun_version, self.apprun_debug)
        patcher = ExecutablesPatcher()

        executables = self._find_executables(scanner)
        embed_archs = self._find_embed_archs(executables)
        if self.deploy_hooks:
            self._deploy_apprun_hooks(resolver, runtime_env, embed_archs)

        self._patch_interpreted_executables(executables, patcher)
        self._link_interpreters_from_runtimes(patcher.used_interpreters_paths)
        self._create_default_runtime(runtime_env)
        self._setup_path_mappings(runtime_env, patcher.used_interpreters_paths.values())
        self._write_appdir_env(runtime_env)
        self._deploy_apprun(resolver)

    def _get_preserve_files(self):
        preserve_files = []
        base_paths = [
            self.finder.base_path,
            self.finder.base_path / "runtime" / "compat",
        ]
        for pattern in self.preserve_paths:
            for base_path in base_paths:
                for match in base_path.glob(pattern):
                    if match.is_dir():
                        preserve_files.extend(match.glob("**/*"))
                    else:
                        preserve_files.append(match)
        return preserve_files

    def _setup_path_mappings(self, runtime_env, interpreter_paths: list):
        # map used interpreters
        interpreter_paths = sorted(set(interpreter_paths))
        for path in interpreter_paths:
            runtime_env.append(self.path_mappings_env, "/" + path + ":$APPDIR/" + path)

        # map build dir to allow caches to work
        runtime_env.append(
            self.path_mappings_env, self.appdir_path.__str__() + ":$APPDIR"
        )

    def _patch_interpreted_executables(self, executables, patcher: ExecutablesPatcher):
        interpreted_executables = [
            executable
            for executable in executables
            if isinstance(executable, InterpretedExecutable)
        ]

        preserve_files = self._get_preserve_files()
        for executable in interpreted_executables:
            allowed = True
            for preserve_file in preserve_files:
                if preserve_file.samefile(executable):
                    allowed = False
                    break
            if allowed:
                patcher.patch_interpreted_executable(executable.path)

    def _find_embed_archs(self, executables):
        embed_archs = set()
        for executable in executables:
            if isinstance(executable, BinaryExecutable):
                embed_archs.add(executable.arch)
        if not embed_archs:
            raise RuntimeError("Unable to determine the bundle architecture")

        return embed_archs

    def _find_executables(self, scanner):
        executables = []
        files = self.finder.find("*", [Finder.is_file, Finder.is_executable])
        for file in files:
            new_executables = scanner.scan_file(file)
            executables.extend(new_executables)

        return executables

    def _configure_runtime_environment(self):
        bundle_id = "".join(
            random.SystemRandom().choice(string.ascii_letters + string.digits)
            for _ in range(7)
        )

        global_env = Environment(
            {
                "APPIMAGE_UUID": bundle_id,
                "XDG_DATA_DIRS": [
                    "$APPDIR/usr/local/share",
                    "$APPDIR/usr/share",
                    "$XDG_DATA_DIRS",
                ],
                "XDG_CONFIG_DIRS": ["$APPDIR/etc/xdg", "$XDG_CONFIG_DIRS"],
                "APPDIR_LIBRARY_PATH": self._get_appdir_library_paths(),
                "PATH": [*self._get_bin_paths(), "$PATH"],
            }
        )

        preserve_files = self._get_preserve_files()
        self._run_configuration_helpers(global_env, preserve_files)
        for k, v in self.user_env.items():
            if k in global_env:
                logging.info("Overriding runtime environment %s" % k)

            global_env.set(k, v)

        global_env.set(self.path_mappings_env, self.path_mappings)

        return global_env

    def _run_configuration_helpers(self, global_env, preserve_files: [Path]):
        execution_list = [
            helpers.GdkPixbuf,
            helpers.GLib,
            helpers.GStreamer,
            helpers.Gtk,
            helpers.LibC,
            helpers.Java,
            helpers.LibGL,
            helpers.OpenSSL,
            helpers.Python,
            helpers.Qt,
        ]

        for helper in execution_list:
            logging.info("Running configuration helper: %s" % helper.__name__)
            inst = helper(self.appdir_path, self.finder)
            inst.configure(global_env, preserve_files)

    def _deploy_apprun(self, resolver: AppRunBinariesResolver):
        bin_path = self.appdir_path / self.main_exec
        if not elf.has_magic_bytes(bin_path):
            raise RuntimeError(f"Main executable is not an elf executable: {bin_path}")

        main_arch = elf.get_arch(bin_path)

        target_path = self.appdir_path / "AppRun"
        apprun_path = resolver.resolve_executable(main_arch)
        shutil.copyfile(apprun_path, target_path, follow_symlinks=True)

        file_utils.set_permissions_rx_all(target_path)

    def _write_appdir_env(self, global_environment):
        apprun_env = Environment(
            {
                "APPDIR": "$ORIGIN/",
                "APPIMAGE_UUID": None,
                "APPDIR_EXEC_PATH": "$APPDIR/" + self.main_exec,
                "APPDIR_EXEC_ARGS": self.main_exec_args,
            }
        )

        apprun_env.merge(global_environment)
        apprun_env.merge(self.user_env)
        apprun_env.drop_empty_keys()

        with open(self.appdir_path / "AppRun.env", "w") as f:
            appdir_path_str = str(self.appdir_path)
            result = apprun_env.serialize()
            result = result.replace(appdir_path_str, "$APPDIR")
            # restore build dir mapping if exists
            result = result.replace("$APPDIR:$APPDIR;", appdir_path_str + ":$APPDIR;")
            f.write(result)

    def parse_env_input(self, user_env_input):
        env = dict()
        for k, v in user_env_input.items():
            if isinstance(v, str):
                v = v.replace("$APPDIR", self.appdir_path.__str__())
                v = v.replace("${APPDIR}", self.appdir_path.__str__())

                if (
                    k == "PATH"
                    or k == "APPDIR_LIBRARY_PATH"
                    or k == "APPDIR_LIBC_LIBRARY_PATH"
                ):
                    v = v.split(":")

            env[k] = v

        return env

    def _deploy_apprun_hooks(
        self,
        apprun_binaries_resolver: AppRunBinariesResolver,
        runtime_env: Environment,
        embed_archs: [str],
    ):

        for arch in embed_archs:
            dir_path = self.appdir_path / "lib" / arch
            dir_path.mkdir(parents=True, exist_ok=True)

            target_path = dir_path / "libapprun_hooks.so"
            source_path = apprun_binaries_resolver.resolve_hooks_library(arch)
            shutil.copy2(source_path, target_path, follow_symlinks=True)

            runtime_env.append("APPDIR_LIBRARY_PATH", str(dir_path))

    def _get_appdir_library_paths(self):
        paths = list(
            self.finder.find_dirs_containing(
                pattern="*.so*",
                file_checks=[Finder.is_file, Finder.is_elf_shared_lib],
                excluded_patterns=[
                    "*/runtime/*",
                    "*/qt5/plugins*",
                    "*/perl*",
                    "*/perl-base*",
                    "*/gio/modules",
                    "*/gtk-*/modules",
                    "*/libgtk-*-0",
                ],
            )
        )
        paths = set([path.__str__() for path in paths])
        return sorted(paths)

    def _get_bin_paths(self):
        paths = set(
            self.finder.find_dirs_containing(
                pattern="*",
                file_checks=[Finder.is_file, Finder.is_executable],
                excluded_patterns=["*/runtime/compat*"],
            )
        )
        return sorted([path.__str__() for path in paths])

    def _create_default_runtime(self, runtime_env):
        self.default_runtime_path.mkdir(parents=True, exist_ok=True)

        ld_paths = runtime_env.get("APPDIR_LIBC_LINKER_PATH")
        for ld_path in ld_paths:
            default_path = self.default_runtime_path / ld_path
            if not default_path.exists():
                default_path.parent.mkdir(exist_ok=True, parents=True)
                default_path.symlink_to("/" + ld_path)

    def _link_interpreters_from_runtimes(self, used_interpreters_paths: dict):
        exported_interpreters = set()
        for exec_path, interp_path in used_interpreters_paths.items():
            if interp_path not in exported_interpreters:
                exported_interpreters.add(interp_path)

                compat_path = self.compat_runtime_path / interp_path
                default_path = self.default_runtime_path / interp_path

                compat_path.parent.mkdir(parents=True, exist_ok=True)
                default_path.parent.mkdir(parents=True, exist_ok=True)

                in_bundle_path = self.appdir_path / interp_path
                if in_bundle_path.exists():
                    nesting_count = str(interp_path).count("/") + 2
                    link_target = "../" * nesting_count + interp_path

                    logging.info('Setup bundled interpreter: "%s"' % interp_path)
                else:
                    link_target = "/" + interp_path
                    logging.info('Setup system interpreter: "%s"' % interp_path)
                    logging.warning(
                        '"%s" will not run if "%s" is not present in the target system'
                        % (exec_path, interp_path)
                    )

                compat_path.symlink_to(link_target)
                default_path.symlink_to(link_target)
