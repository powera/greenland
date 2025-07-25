# set default model
#MODEL = "claude-3-5-haiku-20241022"
#MODEL = "gpt-4o-mini"
MODEL = "gpt-4.1-nano"

import wordfreq.translation.client
cl = wordfreq.translation.client.LinguisticClient(model=MODEL)
get_session = cl.get_session
session = get_session()

import wordfreq.dictionary.reviewer
rv = wordfreq.dictionary.reviewer.LinguisticReviewer()

import wordfreq.storage.database

import wordfreq.translation.processor
prcs = wordfreq.translation.processor.WordProcessor(model=MODEL)

# imports for benchmarks
import lib.run_benchmark
import lib.benchmarks.registry