#!/bin/bash
echo "Generating MacOS ICNS file from input image..."
input="${1}"
if [[ ! -f "$input" ]]; then
	echo "❌ Input file does not exist: $input"
	exit 1
fi

if ! command -v sips; then
	echo "❌ 'sips' command not found. This script requires macOS."
	exit 1
fi

ICON_NAME="${input%.*}.icns"
ICONS_DIR="tempicon.iconset"
mkdir -p $ICONS_DIR
if ! sips -s format png -z 1024 1024 "$input" --out "$ICONS_DIR/icon_512x512@2x.png"; then
	echo "❌ Failed to create icon_512x512@2x.png"
	exit 1
fi
sips -s format png -z 512 512 "$ICONS_DIR/icon_512x512@2x.png" --out "$ICONS_DIR/icon_512x512.png"
sips -s format png -z 512 512 "$ICONS_DIR/icon_512x512@2x.png" --out "$ICONS_DIR/icon_256x256@2x.png"
sips -s format png -z 256 256 "$ICONS_DIR/icon_512x512@2x.png" --out "$ICONS_DIR/icon_256x256.png"
sips -s format png -z 256 256 "$ICONS_DIR/icon_512x512@2x.png" --out "$ICONS_DIR/icon_128x128@2x.png"
sips -s format png -z 128 128 "$ICONS_DIR/icon_512x512@2x.png" --out "$ICONS_DIR/icon_128x128.png"
sips -s format png -z 64 64 "$ICONS_DIR/icon_512x512@2x.png" --out "$ICONS_DIR/icon_64x64.png"
sips -s format png -z 32 32 "$ICONS_DIR/icon_512x512@2x.png" --out "$ICONS_DIR/icon_32x32.png"
sips -s format png -z 32 32 "$ICONS_DIR/icon_512x512@2x.png" --out "$ICONS_DIR/icon_16x16@2x.png"
sips -s format png -z 16 16 "$ICONS_DIR/icon_512x512@2x.png" --out "$ICONS_DIR/icon_16x16.png"
if ! iconutil -c icns $ICONS_DIR; then
	echo "❌ Failed to create ICNS file"
	exit 1
fi
rm -rf $ICONS_DIR
mv tempicon.icns "$ICON_NAME"
