#!/bin/bash
# Rewrite absolute Homebrew dylib load paths in a built .app to @rpath so the
# bundled copies are used.  Required for the sandboxed Mac App Store build:
# the App Sandbox blocks reading /usr/local/** and /opt/homebrew/**, so any
# Mach-O still referencing those paths fails to dlopen (e.g. Pillow's _imaging
# -> libxcb -> libXau), silently breaking graph image copy/save.
#
# Usage: dev/fix-dylib-paths.sh path/to/app.app
set -uo pipefail

APP="${1:?usage: fix-dylib-paths.sh <app-bundle>}"
FW="${APP}/Contents/Frameworks"
if [[ ! -d "${FW}" ]]; then
	echo "No Frameworks dir at ${FW}"
	exit 1
fi

# A dylib is "bundled" if a file with that basename exists at the top level of
# Frameworks.  (Stock macOS bash is 3.2 and lacks associative arrays, so test
# the filesystem directly instead of building a set.)
fixed=0
missing=0

while IFS= read -r -d '' macho; do
	rel="${macho#"${APP}/"}"

	# Fix the library's own id (LC_ID_DYLIB) when it is an absolute Homebrew path.
	id_line=$(otool -D "${macho}" 2>/dev/null | sed -n '2p')
	case "${id_line}" in
	/usr/local/* | /opt/homebrew/*)
		install_name_tool -id "@rpath/$(basename "${id_line}")" "${macho}" &&
			fixed=$((fixed + 1))
		;;
	esac

	# Fix each dependent load command pointing at a Homebrew path.
	deps=$(otool -L "${macho}" 2>/dev/null | tail -n +2 | awk '{print $1}' |
		grep -E '^(/usr/local/|/opt/homebrew/)')
	while IFS= read -r dep; do
		[[ -n "${dep}" ]] || continue
		base=$(basename "${dep}")
		if [[ -f "${FW}/${base}" ]]; then
			install_name_tool -change "${dep}" "@rpath/${base}" "${macho}" &&
				fixed=$((fixed + 1))
		else
			echo "MISSING from bundle: ${base} (referenced by ${rel})"
			missing=$((missing + 1))
		fi
	done <<<"${deps}"
done < <(find "${FW}" \( -name "*.dylib" -o -name "*.so" \) -print0)

echo "Rewrote ${fixed} load command(s)."
if [[ "${missing}" -gt 0 ]]; then
	echo "ERROR: ${missing} referenced dylib(s) are not bundled; copy them into ${FW} and re-run."
	exit 2
fi

remaining=0
while IFS= read -r -d '' f; do
	if otool -L "${f}" 2>/dev/null | tail -n +2 | grep -Eq '/usr/local/|/opt/homebrew/'; then
		remaining=$((remaining + 1))
		echo "STILL ABSOLUTE: ${f#"${APP}/"}"
	fi
done < <(find "${FW}" \( -name "*.dylib" -o -name "*.so" \) -print0)

if [[ "${remaining}" != "0" ]]; then
	echo "ERROR: ${remaining} file(s) still reference absolute Homebrew paths."
	exit 3
fi
echo "OK: no absolute Homebrew dylib references remain."
