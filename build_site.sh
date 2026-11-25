#!/bin/sh
# Puts the web page and the Python card reader together in _site/ (what GitHub Pages serves).
set -e
rm -rf _site
mkdir -p _site
cp -r web/. _site/
cp card.py _site/
touch _site/.nojekyll
