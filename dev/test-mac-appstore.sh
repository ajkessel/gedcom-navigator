#!/bin/bash
if [[ "$OSTYPE" != "darwin"* ]]; then
	echo 'This script is intended to be run on macOS.'
	exit 1
fi
echo "Testing app store connection."
apiKey=$(cat "${HOME}/.appstoreconnect/apikey.txt")
apiIssuer=$(cat "${HOME}/.appstoreconnect/apiissuer.txt")
appid=$(cat "${HOME}/.appstoreconnect/appid.txt")
xcrun altool --list-apps --type osx --apiKey "${apiKey}" --apiIssuer "${apiIssuer}"
