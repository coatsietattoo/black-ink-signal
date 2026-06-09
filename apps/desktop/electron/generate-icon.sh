#!/bin/bash
# Generate macOS .icns icon from SVG
# Requires: Inkscape or rsvg-convert (librsvg), and iconutil (macOS built-in)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ASSETS_DIR="$SCRIPT_DIR/../assets"
SVG="$ASSETS_DIR/icon.svg"
ICONSET="$ASSETS_DIR/icon.iconset"

echo "Generating macOS icon from SVG..."

# Create iconset directory
rm -rf "$ICONSET"
mkdir -p "$ICONSET"

# Generate PNG at all required sizes
SIZES="16 32 64 128 256 512 1024"
for SIZE in $SIZES; do
    echo "  ${SIZE}x${SIZE}..."

    # Try sips (macOS built-in) with a temp PNG, or rsvg-convert, or Inkscape
    if command -v rsvg-convert &>/dev/null; then
        rsvg-convert -w $SIZE -h $SIZE "$SVG" > "$ICONSET/icon_${SIZE}x${SIZE}.png"
    elif command -v inkscape &>/dev/null; then
        inkscape -w $SIZE -h $SIZE "$SVG" -o "$ICONSET/icon_${SIZE}x${SIZE}.png" 2>/dev/null
    elif command -v magick &>/dev/null; then
        magick -background none -density 300 "$SVG" -resize ${SIZE}x${SIZE} "$ICONSET/icon_${SIZE}x${SIZE}.png"
    else
        echo "ERROR: Need rsvg-convert, inkscape, or imagemagick (magick)"
        exit 1
    fi
done

# Rename to Apple's expected format
cd "$ICONSET"
cp icon_16x16.png   icon_16x16.png
cp icon_32x32.png   icon_16x16@2x.png
cp icon_32x32.png   icon_32x32.png
cp icon_64x64.png   icon_32x32@2x.png
cp icon_128x128.png icon_128x128.png
cp icon_256x256.png icon_128x128@2x.png
cp icon_256x256.png icon_256x256.png
cp icon_512x512.png icon_256x256@2x.png
cp icon_512x512.png icon_512x512.png
cp icon_1024x1024.png icon_512x512@2x.png

# Remove non-standard sizes
rm -f icon_64x64.png icon_1024x1024.png

# Create .icns
echo "Creating .icns..."
iconutil -c icns "$ICONSET" -o "$ASSETS_DIR/icon.icns"

# Also create icon.png for Linux
cp "$ICONSET/icon_512x512.png" "$ASSETS_DIR/icon.png"

# Cleanup
rm -rf "$ICONSET"

echo "✓ Icon generated: $ASSETS_DIR/icon.icns"
echo "✓ Linux icon: $ASSETS_DIR/icon.png"
