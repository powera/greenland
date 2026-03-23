from benchmarks.server.analysis import analyze_run_details


def test_analyze_run_details_ignores_slow_incorrect_latency_outlier():
    details = [
        {"question_id": "q1", "score": 100, "eval_msec": 800, "cost_usd": 0.0001},
        {"question_id": "q2", "score": 0, "eval_msec": 30_000, "cost_usd": 0.0001},
        {"question_id": "q3", "score": 100, "eval_msec": 820, "cost_usd": 0.0001},
    ]

    metrics = analyze_run_details(
        "0016_antonym",
        details,
        model_path="gpt-5-mini",
        model_type="remote",
    )

    assert metrics.outlier_count == 1
    assert round(metrics.median_time_msec, 1) == 810.0
    assert round(metrics.avg_time_msec, 1) == 810.0


def test_analyze_run_details_recomputes_score_after_question_exclusion():
    details = [
        {"question_id": "q1", "score": 100, "eval_msec": 800, "cost_usd": 0.0001},
        {
            "question_id": "q2",
            "score": 0,
            "eval_msec": 900,
            "cost_usd": 0.0001,
            "is_question_excluded": True,
        },
    ]

    metrics = analyze_run_details(
        "0016_antonym",
        details,
        model_path="gpt-5-mini",
        model_type="remote",
    )

    assert metrics.effective_score == 100
    assert metrics.included_question_count == 1
    assert metrics.excluded_question_count == 1


def test_analyze_run_details_flags_bad_price_data_with_estimated_token_split():
    details = [
        {
            "question_id": "q1",
            "score": 100,
            "eval_msec": 800,
            "cost_usd": 0.02,
            "tokens_used": 1000,
        }
    ]

    metrics = analyze_run_details(
        "0016_antonym",
        details,
        model_path="gpt-5-mini",
        model_type="remote",
    )

    assert metrics.price_diagnostics.has_mismatch is True
    assert metrics.price_diagnostics.coverage == "estimated"
