#!/usr/bin/env python

# This is a shim to hopefully allow Github to detect the package, build is done with poetry

from setuptools import setup, find_packages

if __name__ == "__main__":
    setup(
        name="baidupcs-py", 
        version="0.7.6", 
        packages=find_packages(exclude=["imgs"]), 
        package_data={
            "": ["*.pyx"],  # Include all .pyx files
            "baidupcs_py": ["**/*.pyx"],  # Include .pyx files in subdirectories
            "common": ["*.pyx", "**/*.pyx"],  # Include .pyx in common folder
            "baidupcs_py.common": ["*.pyx", "**/*.pyx"],  # Include .pyx in common folder
        },
        include_package_data=True,
    )
