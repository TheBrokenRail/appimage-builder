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
import fnmatch

from appimagebuilder.modules.deploy import FileDeploy
from appimagebuilder.context import BundleInfo
from appimagebuilder.modules.deploy.files.shared_object_dependencies_resolver import (
    SharedObjectDependenciesResolver,
)
from appimagebuilder.modules.generate.recipe_sections.package_manager_recipe_section_generator import (
    PackageManagerSectionGenerator,
)
from appimagebuilder.utils import elf


class FilesSectionGenerator(PackageManagerSectionGenerator):
    def __init__(self):
        self.exclusion_patterns = set(FileDeploy.listings["graphics"])
        self.exclusion_patterns = self.exclusion_patterns.union(
            [
                # cache files should not be bundle as they will be rebuilt in the host system
                "/var/cache/**/*",
                # fonts cache files
                "/**/fonts/**/*.cache",
                "/**/fonts/**/.uuid",
                "/**/fonts/.uuid",
                # generic icons mime type
                "**/share/mime/generic-icons",
                # gconv cache
                "**/lib/**/gconv-modules.cache",
                # exclude zoneinfo
                "/usr/share/zoneinfo/**",
                # exclude DRI libs
                "**/lib/**/dri/*.so",
            ]
        )

    def id(self) -> str:
        return "files"

    def generate(self, dependencies: [str], bundle_info: BundleInfo) -> ({}, [str]):
        include_list = set(
            [str(path) for path in dependencies if not self._is_file_blacklisted(path)]
        )

        filtered_include_list = self.filter_linked_libraries(include_list)

        result = {
            "include": sorted(filtered_include_list),
            "exclude": [
                "usr/share/man",
                "usr/share/doc/*/README.*",
                "usr/share/doc/*/changelog.*",
                "usr/share/doc/*/NEWS.*",
                "usr/share/doc/*/TODO.*",
            ],
        }
        return result, []

    def _is_file_blacklisted(self, file_name):
        for pattern in self.exclusion_patterns:
            if fnmatch.fnmatch(file_name, pattern):
                return True
        return False

    def filter_linked_libraries(self, include_list):
        so_files = [file for file in include_list if elf.has_magic_bytes(file)]

        resolver = SharedObjectDependenciesResolver()
        dependencies, _ = resolver.get_dependencies_map(so_files)
        for file in dependencies:
            if file in include_list:
                include_list.remove(file)

        return include_list
