#!/usr/bin/env bash
set -e

mkdir -p assets

magick convert -size 1200x1200 xc:none \
  -fill white -draw "ellipse 600,555 260,270 0,360" \
  -fill none -draw "ellipse 600,555 240,250 0,360" \
  -alpha copy assets/circle_mask_1200.png

echo "Mask generated at assets/circle_mask_1200.png"
