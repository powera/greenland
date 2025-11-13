import constants

import benchmarks.schema.load_schema
benchmarks.schema.load_schema.create_tables()

import benchmarks.schema.create_models
benchmarks.schema.create_models.create_models()

import benchmarks.datastore.common
from lib.benchmarks.factory import get_generator

session = benchmarks.datastore.common.create_dev_session()