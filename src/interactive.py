# set default model
# MODEL = "claude-3-5-haiku-20241022"
# MODEL = "gpt-4o-mini"
MODEL = "gpt-4.1-nano"

import wordfreq.translation.client

cl = wordfreq.translation.client.LinguisticClient(model=MODEL)
get_session = cl.get_session
session = get_session()

import storage.database
import benchmarks.lib.utils.registry

# imports for benchmarks
import benchmarks.run_benchmark
