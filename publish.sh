#!/bin/sh
set -e

python3 setup.py sdist bdist_wheel
twine upload dist/* --skip-existing
rm -r dist build
