#!/usr/bin/env bash
# Run the main Greenland agents for a specific lemma GUID.
# Usage: scripts/activate_guid.sh [-y|--assume-yes] N06_001
#
# Flags:
#   -y, --assume-yes       - Run without interactive confirmation between steps.
#
# Environment overrides:
#   LANGUAGES              - Space-separated list of languages for all applicable steps (default: "lt zh fr es")
#   SENTENCE_COUNT         - Number of sentences to generate per lemma (default: 3)
#   SENTENCE_TRANSLATION_LIMIT - Target count of fully translated sentences per lemma (optional)
#   GRAMMAR_FACT_TYPES     - Space-separated fact types for Lape (optional; overrides grouped tasks)
#   GRAMMAR_FACT_TASK      - Lape grouped task preset (default: "all")
#   AUDIO_VOICES           - Optional voice names for Vieversys (space-separated, e.g., "ash alloy nova")

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

# Set PYTHONPATH to include src/ directory
export PYTHONPATH="${REPO_ROOT}/src"

LANGUAGES=${LANGUAGES:-"lt zh fr es"}
SENTENCE_COUNT=${SENTENCE_COUNT:-3}
SENTENCE_TRANSLATION_LIMIT=${SENTENCE_TRANSLATION_LIMIT:-""}
GRAMMAR_FACT_TYPES=${GRAMMAR_FACT_TYPES:-""}
GRAMMAR_FACT_TASK=${GRAMMAR_FACT_TASK:-"all"}
AUDIO_VOICES=${AUDIO_VOICES:-""}

read -r -a LANGUAGE_LIST <<< "$LANGUAGES"
if [[ -n "${GRAMMAR_FACT_TYPES// }" ]]; then
  read -r -a GRAMMAR_FACT_TYPE_LIST <<< "$GRAMMAR_FACT_TYPES"
else
  GRAMMAR_FACT_TYPE_LIST=()
fi

SENTENCE_LANGUAGE_LIST=("${LANGUAGE_LIST[@]}")
NEEDS_SENTENCE_EN=true
for lang in "${SENTENCE_LANGUAGE_LIST[@]}"; do
  if [[ "$lang" == "en" ]]; then
    NEEDS_SENTENCE_EN=false
    break
  fi
done
if [[ "$NEEDS_SENTENCE_EN" == true ]]; then
  SENTENCE_LANGUAGE_LIST+=("en")
fi

SENTENCE_TRANSLATION_ARGS=()
if [[ -n "$SENTENCE_TRANSLATION_LIMIT" ]]; then
  SENTENCE_TRANSLATION_ARGS+=(--translation-limit "$SENTENCE_TRANSLATION_LIMIT")
fi

run_step() {
  local title="$1"
  shift
  echo ""
  echo "=== ${title} ==="
  echo "Command: $*"
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
# Always include English for vilkas to generate English forms
VILKAS_LANGUAGES=("${LANGUAGE_LIST[@]}")
NEEDS_VILKAS_EN=true
for lang in "${VILKAS_LANGUAGES[@]}"; do
  if [[ "$lang" == "en" ]]; then
    NEEDS_VILKAS_EN=false
    break
  fi
done
if [[ "$NEEDS_VILKAS_EN" == true ]]; then
  VILKAS_LANGUAGES+=("en")
fi

run_step "Grammatical forms" \
  python -m agents.vilkas.cli --guid "$GUID" --task all --fix --languages ${VILKAS_LANGUAGES[*]} --yes

# Synonyms and alternative forms (Šernas)
# Always include English for sernas to generate English synonyms
SERNAS_LANGUAGES=("${LANGUAGE_LIST[@]}")
NEEDS_SERNAS_EN=true
for lang in "${SERNAS_LANGUAGES[@]}"; do
  if [[ "$lang" == "en" ]]; then
    NEEDS_SERNAS_EN=false
    break
  fi
done
if [[ "$NEEDS_SERNAS_EN" == true ]]; then
  SERNAS_LANGUAGES+=("en")
fi

run_step "Synonyms" \
  python -m agents.sernas.cli --guid "$GUID" --mode populate-only --languages ${SERNAS_LANGUAGES[*]} --yes

run_step "Pattern sentences" \
  python -m agents.buivolas --guid "$GUID" --task generate-sentences --mode pattern

# Grammatical facts (Lape) - run once across languages and supported tasks
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

if [[ ${#GRAMMAR_FACT_TYPE_LIST[@]} -gt 0 ]]; then
  for fact_type in "${GRAMMAR_FACT_TYPE_LIST[@]}"; do
    run_step "Grammatical facts (languages: ${LAPE_LANGUAGES[*]} - ${fact_type})" \
      python -m agents.lape --guid "$GUID" --fact-type "$fact_type" --languages ${LAPE_LANGUAGES[*]}
  done
else
  run_step "Grammatical facts (languages: ${LAPE_LANGUAGES[*]} - task: ${GRAMMAR_FACT_TASK})" \
    python -m agents.lape --guid "$GUID" --task "$GRAMMAR_FACT_TASK" --languages ${LAPE_LANGUAGES[*]}
fi

run_step "Sentences" \
  python -m agents.buivolas --guid "$GUID" --task generate-sentences --mode llm --num-sentences "$SENTENCE_COUNT" --language ${SENTENCE_LANGUAGE_LIST[*]}

run_step "Sentence translations" \
  python -m agents.zvirblis --guid "$GUID" --languages ${SENTENCE_LANGUAGE_LIST[*]} ${SENTENCE_TRANSLATION_ARGS[@]+"${SENTENCE_TRANSLATION_ARGS[@]}"}

# Audio generation (Vieversys - OpenAI TTS with S3 upload)
for lang in "${LANGUAGE_LIST[@]}"; do
  if [[ -n "$AUDIO_VOICES" ]]; then
    run_step "Audio (Vieversys - ${lang})" \
      python -m agents.vieversys --guid "$GUID" --mode populate-only --language "$lang" --voices ${AUDIO_VOICES} --upload-s3 --yes
  else
    run_step "Audio (Vieversys - ${lang})" \
      python -m agents.vieversys --guid "$GUID" --mode populate-only --language "$lang" --upload-s3 --yes
  fi
done
