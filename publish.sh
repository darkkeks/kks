#!/bin/sh
set -e

rm -r dist
python3 setup.py sdist bdist_wheel
twine upload dist/*
