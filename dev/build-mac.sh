#!/bin/bash
if [[ "$OSTYPE" != "darwin"* ]]; then
	echo 'This script is intended to be run on macOS.'
	exit 1
fi
output_file="gedcom-navigator-mac.zip"
while getopts "hnco:" opt; do
	case $opt in
	h)
		echo "Usage: $0 [-h] [-n] [-c] [-o]"
		echo "  -h  Show this help message and exit"
		echo "  -n  Dry run: build the app but skip notarization and stapling"
		echo "  -c  Clean build: remove virtual environment and pyenv versions before building"
		echo "  -o  Specify output file name (default: gedcom-navigator-mac.zip)"
		exit 0
		;;
	n) DRY=true ;;
	c) CLEAN=true ;;
	o) output_file=$OPTARG ;;
	*)
		echo "Invalid option"
		exit 1
		;;
	esac
done
echo 'Building for macOS...'
[[ "$CLEAN" ]] && {
	echo 'Warning: this will delete the current .venv and any .pyenv in your home folder.'
	read -t 5 -n 1 -s -r -p "Press any key to continue or q to exit (waiting 5s)..." x
	[ "${x}" == "q" ] && exit 1
	rm -r ./.venv "${HOME}/.pyenv"
}
if [[ -e "${HOME}/.config/p" ]]; then
	echo 'Local keychain password found, unlocking keychain...'
	security unlock-keychain -p "$(cat "${HOME}"/.config/p)" "${HOME}/Library/Keychains/login.keychain-db"
else
	echo 'Password file not found at ~/.config/p, skipping automatic keychain unlock.'
	security unlock-keychain "${HOME}/Library/Keychains/login.keychain-db"
fi
export PATH="/usr/local/bin:$PATH"
if command -v brew >/dev/null 2>&1; then
	brew_prefix=$(brew --prefix python)
	export PATH="$brew_prefix/libexec/bin:$PATH"
else
	echo 'homebrew not found, we will still try to build but this script has not been tested on MacOS without brew.'
fi

# preference is for universal2 python from python.org
# alternatively, set up pyenv environment
if [ -e "/Library/Frameworks/Python.framework/Versions/current/bin/python3" ]; then
	export PATH="/Library/Frameworks/Python.framework/Versions/current/bin/:${PATH}"
else
	echo 'Python from python.org not found, attempting to set up pyenv...'
	command -v pyenv || {
		echo 'pyenv missing, attempting to install from homebrew...'
		brew install pyenv
	}
	export PYENV_ROOT="$HOME/.pyenv"
	[[ -e "${PYENV_ROOT}/shims/python3.14" ]] || {
		echo 'Installing pyenv for python 3.14'
		mkdir -p "${PYENV_ROOT}"
		eval "$(pyenv init -)"
		pyenv install 3.14
		pyenv global 3.14
	}
	eval "$(pyenv init -)"
fi
./dev/generate-icns.sh ./icons/family_tree.png || {
	echo 'Failed to generate ICNS file.'
	exit 1
}
[[ -e .venv/bin/activate ]] || {
	echo 'Creating virtual environment...'
	python3 -m venv .venv --prompt "gedcom-navigator" || {
		echo 'Failed to create virtual environment.'
		exit 1
	}
}
# shellcheck disable=SC1091
source .venv/bin/activate || {
	echo 'Failed to activate virtual environment.'
	exit 1
}
# It's necessary to build from source and disable default-const-init-var-unsafe due to recent xcode changes
# issue filed at https://github.com/ronaldoussoren/pyobjc/issues/673
env CFLAGS="-Wno-error=default-const-init-var-unsafe" ARCHFLAGS="-arch arm64 -arch x86_64" pip install -r ./dev/requirements-dev.txt --no-binary :all: || {
	echo 'Failed to install dependencies.'
	exit 1
}
echo 'Patching ctktooltip... (see https://github.com/Akascape/CTkToolTip/issues/20 for details)'
patch -d "${VIRTUAL_ENV}/lib/site-packages/" -N -p1 < ./dev/ctk_tooltip.patch || {
	echo 'Failed to patch ctktooltip, may have been applied already. Proceeding anyway...'
}
echo 'Running unit tests...'
pytest -v --tb=short --disable-warnings || {
	echo 'Unit tests failed. Exiting.'
	exit 1
}
python3 ./dev/generate_icon.py ./icons/family_tree.png || {
	echo 'Failed to generate ICO file.'
	exit 1
}
pyinstaller --noconfirm ./dev/gedcom_navigator_cli.spec || {
	echo 'pyinstaller failed to build CLI.'
	exit 1
}
pyinstaller --noconfirm ./dev/gedcom_navigator_gui.spec || {
	echo 'pyinstaller failed to build GUI.'
	exit 1
}
[ -d "dist" ] || {
	echo 'Cannot find dist build folder.'
	exit 1
}
[ "$DRY" ] && exit 0
ditto -c -k --sequesterRsrc --keepParent "dist/gedcom-navigator.app" "${output_file}" || {
	echo 'Cannot build zip file.'
	exit 1
}
xcrun notarytool submit "${output_file}" --keychain-profile "notarytool-profile" --wait || {
	echo 'Notarytool failed.'
	exit 1
}
xcrun stapler staple ./dist/gedcom-navigator.app || {
	echo 'Stapler failed.'
	exit 1
}
rm "${output_file}"
ditto -c -k --sequesterRsrc --keepParent "dist/gedcom-navigator.app" "${output_file}" || {
	echo 'Cannot build notarized zip file.'
	exit 1
}
mv "${output_file}" dist/
