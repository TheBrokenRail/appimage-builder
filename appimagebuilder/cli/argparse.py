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
import argparse
import os

from appimagebuilder.modules.generate.command_generate import CommandGenerate


def setup_argparser():
    parser = argparse.ArgumentParser(description="AppImage crafting tool")

    parser.add_argument(
        "--recipe",
        dest="recipe",
        default=os.path.join(os.getcwd(), "AppImageBuilder.yml"),
        help="recipe file path (default: $PWD/AppImageBuilder.yml)",
    )
    parser.add_argument(
        "--log",
        dest="loglevel",
        default="INFO",
        help="logging level (default: INFO)",
    )
    parser.add_argument(
        "--skip-script",
        dest="skip_script",
        action="store_true",
        help="[DEPRECATED] Skip script execution",
    )
    parser.add_argument(
        "--skip-build",
        dest="skip_build",
        action="store_true",
        help="[DEPRECATED] Skip AppDir building",
    )
    parser.add_argument(
        "--skip-tests",
        dest="skip_tests",
        action="store_true",
        help="[DEPRECATED] Skip AppDir testing",
    )
    parser.add_argument(
        "--skip-appimage",
        dest="skip_appimage",
        action="store_true",
        help="[DEPRECATED] Skip AppImage generation",
    )
    parser.add_argument(
        "--generate",
        dest="generate",
        action="store_true",
        help="Try to generate recipe from an AppDir",
    )

    subparsers = parser.add_subparsers(help="Command to be executed")
    CommandGenerate.setup_parser(subparsers)

    return parser
