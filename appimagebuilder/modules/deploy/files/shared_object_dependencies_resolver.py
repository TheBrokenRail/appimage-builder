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
import os
import re
import subprocess


class SharedObjectDependenciesResolver:
    def __init__(self, extra_library_paths=None):
        if extra_library_paths is None:
            self._ld_paths = []

        self._ld_paths = extra_library_paths

    def get_dependencies_map(self, shared_object_files):
        dependencies = set()
        duplicates = set()

        for file in shared_object_files:
            if file not in dependencies:
                file_deps = self.list_dependencies(file)
                dependencies = dependencies.union(file_deps)
            else:
                duplicates.add(file)

        return dependencies, duplicates

    def list_dependencies(self, file):
        env = os.environ.copy()
        if self._ld_paths:
            env['LD_LIBRARY_PATH'] = ":".join(self._ld_paths)

        proc = subprocess.run(['ldd', file], capture_output=True, env=env)

        output = proc.stdout.decode()
        return re.findall(r'\s(/.*)\s\(.*\)', output)
