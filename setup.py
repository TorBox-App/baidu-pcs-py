#!/usr/bin/env python

# This is a shim to hopefully allow Github to detect the package, build is done with poetry

from setuptools import setup, find_packages

if __name__ == "__main__":
    setup(name="baidupcs-py", version="0.7.6", packages=find_packages(exclude=["imgs"]))
