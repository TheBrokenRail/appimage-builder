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

from unittest import TestCase

from appimagebuilder.modules.deploy.files.shared_object_dependencies_resolver import SharedObjectDependenciesResolver


class TestSharedObjectDependenciesResolver(TestCase):
    def setUp(self) -> None:
        self.resolver = SharedObjectDependenciesResolver()

    def test_list_dependencies(self):
        dependencies = self.resolver.list_dependencies('/bin/bash')
        self.assertIn('/lib64/ld-linux-x86-64.so.2', dependencies)
