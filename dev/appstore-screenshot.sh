#!/usr/bin/env bash
./start.sh &
osascript -e 'tell application "Python" to set bounds of window 1 to {0,0,1920,1200}'
sleep 10s
screencapture ~/Desktop/screenshot.png
magick screenshot.png -crop 3840x2400+0+55 ~/Desktop/screenshot-crop.png
