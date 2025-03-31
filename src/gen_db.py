import constants

import schema.load_schema
schema.load_schema.create_tables()

import schema.create_models
schema.create_models.create_models()

import datastore.common
from lib.benchmarks.factory import get_generator

session = datastore.common.create_dev_session()

letter_count_generator = get_generator("0012_letter_count", session)
letter_count_generator.load_to_database(count=40, model="gemma2:9b")

spell_check_generator = get_generator("0015_spell_check", session)
spell_check_generator.load_to_database(count=40, model="gemma2:9b")

antonym_generator = get_generator("0016_antonym", session)
antonym_generator.load_to_database(count=40, model="gemma2:9b")

definitions_generator = get_generator("0020_definitions", session)
definitions_generator.load_to_database(count=40, model="gemma2:9b")
