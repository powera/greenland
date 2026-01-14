import benchmarks.schema.load_schema
import benchmarks.benchmark_constants as benchmark_constants

benchmarks.schema.load_schema.create_tables()

import benchmarks.schema.create_models

benchmarks.schema.create_models.create_models()

import benchmarks.datastore.common as datastore_common
from benchmarks.lib.utils.factory import get_generator

session = datastore_common.create_dev_session()
