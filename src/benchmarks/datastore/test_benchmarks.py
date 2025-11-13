import unittest
import os
import json
from datetime import datetime
from benchmarks.datastore.benchmarks import (
    create_database_and_session,
    insert_benchmark,
    insert_question,
    insert_run,
    list_all_benchmarks,
    load_all_questions_for_benchmark
)
from benchmarks.datastore.common import (
    insert_model,
    list_all_models
)

class TestDatastore(unittest.TestCase):
    def setUp(self):
        """
        Create a temporary database for each test
        """
        self.db_path = 'test_benchmarks.sqlite'
        self.session = create_database_and_session(self.db_path)

    def tearDown(self):
        """
        Close the session and remove the temporary database
        """
        self.session.close()
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_insert_benchmark(self):
        """
        Test inserting a benchmark successfully
        """
        success, message = insert_benchmark(
            self.session, 
            'test_benchmark', 
            'Test Benchmark', 
            'A benchmark for testing purposes'
        )
        self.assertTrue(success)
        self.assertIn('successfully inserted', message)

    def test_insert_benchmark_duplicate(self):
        """
        Test inserting a duplicate benchmark
        """
        # First insertion should succeed
        insert_benchmark(
            self.session, 
            'test_benchmark',
            'Test Benchmark',
            'Test Description'
        )
        
        # Second insertion should fail
        success, message = insert_benchmark(
            self.session, 
            'test_benchmark', 
            'Test Benchmark',
            'Test Description'
        )
        self.assertFalse(success)
        self.assertIn('already exists', message)

    def test_insert_model(self):
        """
        Test inserting a model successfully
        """
        success, message = insert_model(
            self.session,
            'test_model',
            'Test Model',
            '2024-01-01',
            100,
            'MIT'
        )
        self.assertTrue(success)
        self.assertIn('successfully inserted', message)

    def test_insert_question(self):
        """
        Test inserting a question with a benchmark
        """
        # First, insert a benchmark
        insert_benchmark(self.session, 'test_benchmark', 'Test Benchmark', 'Test Description')
        
        # Then insert a question
        success, message = insert_question(
            self.session,
            'test_question_1',
            'test_benchmark',
            json.dumps({'difficulty': 'medium', 'category': 'math'})
        )
        self.assertTrue(success)
        self.assertIn('successfully inserted', message)

    def test_insert_run(self):
        """
        Test inserting a run with a model and benchmark
        """
        # First, insert a model and benchmark
        insert_model(self.session, 'test_model', 'Test Model')
        insert_benchmark(self.session, 'test_benchmark', 'Test Benchmark', 'Test Description')
        
        # Then insert a run
        success, run_id = insert_run(
            self.session,
            'test_model',
            'test_benchmark',
            85  # normed_score
        )
        self.assertTrue(success)
        self.assertIsInstance(run_id, int)

    def test_insert_run_with_details(self):
        """
        Test inserting a run with run details
        """
        # Setup: insert model, benchmark, run, and question
        insert_model(self.session, 'test_model', 'Test Model')
        insert_benchmark(self.session, 'test_benchmark', 'Test Benchmark', 'Test Description')
        insert_question(
            self.session,
            'test_question_1',
            'test_benchmark',
            json.dumps({'test': 'data'})
        )
        
        run_details = [{
            "question_id": "test_question_1",
            "score": 1,  # Using binary scoring
            "eval_msec": 1000,
            "debug_json": json.dumps({"test": "debug"})
        }]
        
        success, run_id = insert_run(
            self.session,
            'test_model',
            'test_benchmark',
            85,  # normed_score
            run_details=run_details
        )
        self.assertTrue(success)
        self.assertIsInstance(run_id, int)

    def test_insert_run_with_timestamp(self):
        """
        Test inserting a run with a specific timestamp
        """
        insert_model(self.session, 'test_model', 'Test Model')
        insert_benchmark(self.session, 'test_benchmark', 'Test Benchmark', 'Test Description')
        
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        success, run_id = insert_run(
            self.session,
            'test_model',
            'test_benchmark',
            85,
            run_ts=timestamp
        )
        self.assertTrue(success)
        self.assertIsInstance(run_id, int)

    def test_list_all_models(self):
        """
        Test listing all models
        """
        # Insert multiple models
        insert_model(self.session, 'model1', 'Model One')
        insert_model(self.session, 'model2', 'Model Two')
        
        models = list_all_models(self.session)
        self.assertEqual(len(models), 2)
        self.assertTrue(any(m['codename'] == 'model1' for m in models))
        self.assertTrue(any(m['codename'] == 'model2' for m in models))

    def test_list_all_benchmarks(self):
        """
        Test listing all benchmarks
        """
        insert_benchmark(self.session, 'benchmark1', 'Benchmark One', 'Description 1')
        insert_benchmark(self.session, 'benchmark2', 'Benchmark Two', 'Description 2')
        
        benchmarks = list_all_benchmarks(self.session)
        self.assertEqual(len(benchmarks), 2)
        self.assertTrue(any(b['codename'] == 'benchmark1' for b in benchmarks))
        self.assertTrue(any(b['codename'] == 'benchmark2' for b in benchmarks))

    def test_load_all_questions_for_benchmark(self):
        """
        Test loading all questions for a specific benchmark
        """
        insert_benchmark(self.session, 'test_benchmark', 'Test Benchmark', 'Test Description')
        
        # Insert multiple questions
        questions_data = [
            ('q1', {'type': 'multiple_choice'}),
            ('q2', {'type': 'free_response'}),
        ]
        
        for qid, data in questions_data:
            insert_question(
                self.session,
                f'test_question_{qid}',
                'test_benchmark',
                json.dumps(data)
            )
        
        questions = load_all_questions_for_benchmark(self.session, 'test_benchmark')
        self.assertEqual(len(questions), 2)
        self.assertTrue(any(q['question_id'] == 'test_question_q1' for q in questions))
        self.assertTrue(any(q['question_id'] == 'test_question_q2' for q in questions))


if __name__ == '__main__':
    unittest.main()
