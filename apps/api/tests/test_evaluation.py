from pathlib import Path

from companion.evaluation import run_evaluation


async def test_deterministic_evaluation_meets_locked_acceptance_targets(
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.json"

    report = await run_evaluation(output_path=output)

    assert report.failures == []
    assert report.metrics.persistence_accuracy == 1
    assert report.metrics.contradiction_resolution_accuracy == 1
    assert report.metrics.superseded_leakage_rate == 0
    assert report.metrics.recall_at_5 >= 0.9
    assert report.metrics.persona_contradiction_rate <= 0.02
    assert report.metrics.tone_adherence is None
    assert output.exists()
