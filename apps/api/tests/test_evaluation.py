from pathlib import Path

from companion.evaluation import run_evaluation
from companion.evaluation.live import LIVE_TURNS, _merge_usage


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
    assert report.metrics.precision_at_1 >= 0.9
    assert report.metrics.mean_reciprocal_rank >= 0.9
    assert report.metrics.persona_contradiction_rate <= 0.02
    assert report.metrics.tone_adherence is None
    assert output.exists()


def test_live_evaluation_has_52_ordered_everyday_turns_and_memory_probes() -> None:
    assert len(LIVE_TURNS) == 52
    assert [item.turn_id for item in LIVE_TURNS] == list(range(1, 53))
    assert sum(bool(item.expected_phrases) for item in LIVE_TURNS) >= 10
    assert all("API" not in item.prompt and "password" not in item.prompt for item in LIVE_TURNS)


def test_live_evaluation_usage_discloses_model_failover() -> None:
    combined = _merge_usage(
        {
            "calls": 2,
            "provider": "groq",
            "model": "model-a",
            "input_tokens": 10,
            "output_tokens": 3,
        },
        {
            "calls": 1,
            "provider": "groq",
            "model": "model-b",
            "input_tokens": 5,
            "output_tokens": 2,
        },
    )

    assert combined == {
        "calls": 3,
        "provider": "groq",
        "model": "model-a -> model-b",
        "input_tokens": 15,
        "output_tokens": 5,
    }
