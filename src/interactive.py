#MODEL = "claude-3-5-haiku-20241022"
#MODEL = "gpt-4o-mini"
MODEL = "gpt-4.1-nano"

import wordfreq.linguistic_client
cl = wordfreq.linguistic_client.LinguisticClient(model=MODEL)
get_session = cl.get_session
session = get_session()

import wordfreq.reviewer
rv = wordfreq.reviewer.LinguisticReviewer()

import wordfreq.linguistic_db

import wordfreq.word_processor
prcs = wordfreq.word_processor.WordProcessor(model=MODEL)
