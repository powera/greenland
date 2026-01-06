#!/usr/bin/env bash
# Run the main Greenland agents for a specific lemma GUID.
# Usage: scripts/activate_guid.sh [-y|--assume-yes] N06_001
#
# Flags:
#   -y, --assume-yes       - Run without interactive confirmation between steps.
#
# Environment overrides:
#   LANGUAGES              - Space-separated list of languages for all applicable steps (default: "lt zh ko fr es de pt sw vi")
#   GRAMMAR_FACT_TYPES     - Space-separated fact types for Lape (optional; overrides grouped tasks)
#   GRAMMAR_FACT_TASK      - Lape grouped task preset (default: "all")
#   AUDIO_VOICES           - Optional voice names for Strazdas (space-separated)

set -euo pipefail

ASSUME_YES=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--assume-yes)
      ASSUME_YES=true
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Unknown flag: $1" >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 [-y|--assume-yes] <LEMMA_GUID>" >&2
  exit 1
fi

GUID="$1"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LANGUAGES=${LANGUAGES:-"lt zh ko fr es de pt sw vi"}
GRAMMAR_FACT_TYPES=${GRAMMAR_FACT_TYPES:-""}
GRAMMAR_FACT_TASK=${GRAMMAR_FACT_TASK:-"all"}
AUDIO_VOICES=${AUDIO_VOICES:-""}

read -r -a LANGUAGE_LIST <<< "$LANGUAGES"
if [[ -n "${GRAMMAR_FACT_TYPES// }" ]]; then
  read -r -a GRAMMAR_FACT_TYPE_LIST <<< "$GRAMMAR_FACT_TYPES"
else
  GRAMMAR_FACT_TYPE_LIST=()
fi

run_step() {
  local title="$1"
  shift
  echo "\n=== ${title} ==="
  if [[ "$ASSUME_YES" == true ]]; then
    "$@"
    return
  fi

  read -r -p "Run this step? [y/N] " reply
  if [[ "$reply" =~ ^[Yy]$ ]]; then
    "$@"
  else
    echo "Skipped ${title}"
  fi
}

# Definitions (Lokys) - validates and updates definition text
run_step "Definitions" \
  python -m agents.lokys.cli --guid "$GUID" --check-type definitions

# Translations (Voras) - populate missing translations across languages
run_step "Translations" \
  python -m agents.voras.cli --guid "$GUID" --mode populate-only --languages ${LANGUAGES} --yes

# Grammatical forms (Vilkas) - generate/repair forms for all supported languages
# TODO: Add a language limiter once Vilkas supports selecting from LANGUAGES instead of only task scopes.
run_step "Grammatical forms" \
  python -m agents.vilkas.cli --guid "$GUID" --task all --fix --yes

# Synonyms and alternative forms (Šernas)
run_step "Synonyms" \
  python -m agents.sernas.cli --guid "$GUID" --mode populate-only --languages ${LANGUAGES} --yes

# Grammatical facts (Lape) - run per language
LAPE_LANGUAGES=("${LANGUAGE_LIST[@]}")
NEEDS_EN=true
for lang in "${LAPE_LANGUAGES[@]}"; do
  if [[ "$lang" == "en" ]]; then
    NEEDS_EN=false
    break
  fi
done
if [[ "$NEEDS_EN" == true ]]; then
  LAPE_LANGUAGES+=("en")
fi

for lang in "${LAPE_LANGUAGES[@]}"; do
  if [[ ${#GRAMMAR_FACT_TYPE_LIST[@]} -gt 0 ]]; then
    for fact_type in "${GRAMMAR_FACT_TYPE_LIST[@]}"; do
      run_step "Grammatical facts (${lang} - ${fact_type})" \
        python -m agents.lape --guid "$GUID" --fact-type "$fact_type" --language "$lang"
    done
  else
    run_step "Grammatical facts (${lang} - task: ${GRAMMAR_FACT_TASK})" \
      python -m agents.lape --guid "$GUID" --task "$GRAMMAR_FACT_TASK" --language "$lang"
  fi
done

# TODO: Sentence generation once --guid is supported for the sentence agents
# run_step "Sentences" python -m agents.zvirblis --guid "$GUID" --num-sentences 3
# run_step "Sentence translations" python -m agents.zvirblis --guid "$GUID" --num-sentences 3 --languages en lt

# Audio generation (Strazdas - eSpeak-NG)
for lang in "${LANGUAGE_LIST[@]}"; do
  if [[ -n "$AUDIO_VOICES" ]]; then
    run_step "Audio (Strazdas - ${lang})" \
      python -m agents.strazdas --guid "$GUID" --mode populate-only --language "$lang" --voices ${AUDIO_VOICES} --yes
  else
    run_step "Audio (Strazdas - ${lang})" \
      python -m agents.strazdas --guid "$GUID" --mode populate-only --language "$lang" --yes
  fi
done
