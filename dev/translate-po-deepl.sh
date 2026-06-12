#!/usr/bin/env bash
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1
version=$(git describe --tags --abbrev=0 2>/dev/null || echo "0.0.0")
export $(grep -v '^#' .env | xargs)
[ ! -e ./dev/translate-po-deepl.py ] && {
	echo 'dev/translate-po-deepl.py not found. Exiting.'
	exit 1
}
[[ -e ".venv/bin/activate" ]] || {
	echo 'Creating virtual environment...'
	python3 -m venv .venv --prompt "gedcom-navigator" || {
		echo 'Failed to create virtual environment.'
		exit 1
	}
}
source .venv/bin/activate || {
	echo 'Failed to activate virtual environment.'
	exit 1
}
mkdir -p locales || {
	echo 'Failed to create locales directory.'
	exit 1
}
pybabel extract --copyright-holder="Adam J. Kessel" \
	--project="GEDCOM Navigator" \
	--version="${version}" \
	--msgid-bugs-address="adam@rosi-kessel.org" \
	-o locales/gedcom_navigator.pot src/ \
	src/ || {
	echo "Failed to extract strings with pybabel."
	exit 1
}
python ./dev/translate-po-deepl.py --input ./locales/gedcom_navigator.pot --outdir locales --langs de es fr he --prefer-official
exit_code=$?
if [[ $exit_code -eq 3 ]]; then
	echo 'ERROR: Translation completed but placeholder tokens were not properly restored.'
	echo 'Check the WARNING lines above. The .po files may contain corrupt entries.'
	exit 1
elif [[ $exit_code -ne 0 ]]; then
	echo 'Translation failed. Is API key set in .env?'
	exit 1
fi

# Secondary check: scan output files for any remaining unrestored tokens (⟦NNNN⟧)
token_errors=0
for x in locales/*.po; do
	if grep -qP '⟦\d{4}⟧' "${x}" 2>/dev/null || grep -q '⟦' "${x}" 2>/dev/null; then
		echo "ERROR: ${x} contains unrestored placeholder tokens — translation is corrupt."
		token_errors=$((token_errors + 1))
	fi
done
if [[ $token_errors -gt 0 ]]; then
	echo "ERROR: ${token_errors} file(s) have corrupt translations. Aborting."
	exit 1
fi

for x in locales/*.po; do
	msgfmt --check "${x}" || {
		echo "${x} failed msgfmt check. Exiting."
		continue
	}
	if [[ ! -s "${x}" ]]; then
		echo "${x} is empty, skipping."
		continue
	fi
	if [[ ! "${x}" =~ .*_[a-z]{2}.po ]]; then
		echo "${x} does not match expected pattern, skipping."
		continue
	fi
	echo "${x} found, moving into locale folder."
	lang=$(echo "${x}" | sed -e 's/.*_//g' -e 's/\..*//g')
	mkdir -p "locales/${lang}/LC_MESSAGES"
	mv "${x}" "locales/${lang}/LC_MESSAGES/gedcom_navigator.po"
done
