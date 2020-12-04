#!/bin/sh
set -e

python3 setup.py sdist
twine upload dist/* --skip-existing
rm -r dist build
