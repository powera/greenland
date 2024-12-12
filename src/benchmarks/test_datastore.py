import unittest
import os
import json
from benchmarks.datastore import (
    create_database_and_session,
    insert_benchmark,
    insert_model,
    insert_question,
    insert_run,
    list_all_models,
    find_top_runs_for_benchmark
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

    def test_insert_benchmark_diff_metric(self):
        """
        Test inserting a duplicate benchmark
        """
        # First insertion should succeed
        insert_benchmark(
            self.session, 
            'test_benchmark',
            'answer',
            'Test Benchmark'
        )
        
        # different metric
        success, message = insert_benchmark(
            self.session, 
            'test_benchmark', 
            'politeness',
            'Test Benchmark'
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
            'answer',
            'Test Benchmark'
        )
        
        # Second insertion should fail
        success, message = insert_benchmark(
            self.session, 
            'test_benchmark', 
            'answer',
            'Test Benchmark'
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
        insert_benchmark(self.session, 'test_benchmark', 'answer', 'Test Benchmark')
        
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
        insert_benchmark(self.session, 'test_benchmark', 'answer', 'Test Benchmark')
        
        # Then insert a run
        success, run_id = insert_run(
            self.session,
            'test_model',
            'test_benchmark',
            'answer',
            85
        )
        self.assertTrue(success)
        self.assertIsNotNone(run_id)

    def test_insert_run_detail(self):
        """
        Test inserting a run detail
        """
        # Setup: insert model, benchmark, run, and question
        insert_model(self.session, 'test_model', 'Test Model')
        insert_benchmark(self.session, 'test_benchmark', 'answer', 'Test Benchmark')
        insert_question(
            self.session,
            'test_question_1',
            'test_benchmark'
        )
        success, run_id = insert_run(
            self.session,
            'test_model',
            'test_benchmark',
            'answer',
            85,
            run_details = [{"question_id": "test_question_1", "score": 90, "eval_msec": 1000}]
        )
        self.assertTrue(success)

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

    def test_find_top_runs_for_benchmark(self):
        """
        Test finding top runs for a benchmark
        """
        # Setup: insert model, benchmark, and multiple runs
        insert_model(self.session, 'model1', 'Model One')
        insert_model(self.session, 'model2', 'Model Two')
        insert_benchmark(self.session, 'test_benchmark', 'answer', 'Test Benchmark')
        insert_benchmark(self.session, 'test_benchmark_2', 'answer', 'Second Benchmark')
        
        # Insert runs with different scores
        insert_run(self.session, 'model1', 'test_benchmark', 'answer', 90)
        insert_run(self.session, 'model2', 'test_benchmark', 'answer', 85)
        insert_run(self.session, 'model1', 'test_benchmark_2', 'answer', 95)
        
        top_runs = find_top_runs_for_benchmark(self.session, 'test_benchmark', 'answer')
        
        # Verify top runs are returned in descending order
        self.assertEqual(len(top_runs), 2)
        self.assertEqual(top_runs[0]['normed_score'], 90)
        self.assertEqual(top_runs[1]['normed_score'], 85)

if __name__ == '__main__':
    unittest.main()
