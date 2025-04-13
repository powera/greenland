import constants

import schema.load_schema
schema.load_schema.create_tables()

import schema.create_models
schema.create_models.create_models()

import datastore.common
from lib.benchmarks.factory import get_generator

session = datastore.common.create_dev_session()