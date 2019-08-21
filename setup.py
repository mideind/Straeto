#!/usr/bin/env python
# -*- encoding: utf-8 -*-

"""
    Bus: A package encapsulating information about buses and bus routes

    Setup.py

    Copyright (C) 2019 Miðeind ehf.
    Original Author: Vilhjálmur Þorsteinsson

        This program is free software: you can redistribute it and/or modify
        it under the terms of the GNU General Public License as published by
        the Free Software Foundation, either version 3 of the License, or
        (at your option) any later version.
        This program is distributed in the hope that it will be useful,
        but WITHOUT ANY WARRANTY; without even the implied warranty of
        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
        GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see http://www.gnu.org/licenses/.


    This module sets up the bus package.

"""

from __future__ import print_function
from __future__ import unicode_literals

import io
import re
import sys

from glob import glob
from os.path import basename, dirname, join, splitext

from setuptools import find_packages
from setuptools import setup


if sys.version_info < (3, 4):
    print("Bus requires Python >= 3.4")
    sys.exit(1)


def read(*names, **kwargs):
    try:
        return io.open(
            join(dirname(__file__), *names),
            encoding=kwargs.get("encoding", "utf8")
        ).read()
    except (IOError, OSError):
        return ""


setup(
    name="bus",
    # Remember to modify version numbers in
    # doc/conf.py and src/bus/__init__.py as well
    version="0.0.1",
    license="GNU GPLv3",
    description="A package for information about buses and bus routes",
    long_description="{0}\n{1}".format(
        re.compile("^.. start-badges.*^.. end-badges", re.M | re.S)
            .sub("", read("README.rst")),
        re.sub(":[a-z]+:`~?(.*?)`", r"``\1``", read("CHANGELOG.rst")),
    ),
    author="Miðeind ehf",
    author_email="vt@extrada.com",
    url="https://github.com/mideind/Bus",
    packages=find_packages("src"),
    package_dir={"": "src"},
    py_modules=[splitext(basename(path))[0] for path in glob("src/*.py")],
    include_package_data=True,
    zip_safe=True,
    classifiers=[
        # complete classifier list: http://pypi.python.org/pypi?%3Aaction=list_classifiers
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: Unix",
        "Operating System :: POSIX",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS",
        "Natural Language :: Icelandic",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
    ],
    keywords=["bus", "route", "transportation", "iceland"],
    setup_requires=[],
    install_requires=[],
)