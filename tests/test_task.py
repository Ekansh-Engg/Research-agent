from workers.tasks import simulate_long_task


def test_simulate_long_task_runs_synchronously_in_tests():
    result = simulate_long_task.delay(1)

    assert result.status == "SUCCESS"
    assert result.result == {"status": "complete", "duration": 1}