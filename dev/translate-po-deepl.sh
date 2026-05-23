#!/usr/bin/env bash
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "${SCRIPT_DIR}/.." || exit 1
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
pybabel extract -o locales/gedcom_navigator.pot src/ || {
  echo "Failed to extract strings with pybabel."
  exit 1
}
python ./dev/translate-po-deepl.py --input ./locales/gedcom_navigator.pot --outdir locales --langs de es fr he --prefer-official || {
  echo 'Translation failed. Is API key set in .env?'
  exit 1
}
for x in locales/*.po
do 
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
  lang=$(echo "${x}"|sed -e 's/.*_//g' -e 's/\..*//g')
  mkdir -p "locales/${lang}/LC_MESSAGES"
  mv "${x}" "locales/${lang}/LC_MESSAGES/gedcom_navigator.po"
done
