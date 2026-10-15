from causal_lab.experiments import run_experiments


def test_all_research_hypotheses():
    results = run_experiments()
    assert results["total"] == 4
    assert results["all_passed"], results
