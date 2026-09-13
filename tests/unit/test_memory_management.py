"""Unit tests for Asynchronous Memory Generation & Consolidation in TeamMemoryBank."""

import asyncio

import pytest

from app.sessions import TeamMemoryBank


@pytest.fixture
def clean_memory_bank():
    """Provides an isolated in-memory TeamMemoryBank instance."""
    bank = TeamMemoryBank(project=None)
    # Start with known seeded state
    return bank


@pytest.mark.anyio
async def test_add_memory_async(clean_memory_bank):
    """Test non-blocking asynchronous memory addition."""
    bank = clean_memory_bank
    initial_count = len(bank._memories)

    item = await bank.add_memory_async(
        category="athlete_preferences",
        entity="Gina",
        fact="Prefers matcha green tea after afternoon conditioning sessions.",
        confidence=0.95,
        metadata={"source": "nutritionist_consult"},
    )

    assert item["id"].startswith("mem_")
    assert item["category"] == "athlete_preferences"
    assert item["entity"] == "Gina"
    assert len(bank._memories) == initial_count + 1

    # Verify search finds the new fact
    results = bank.search_memories("matcha")
    assert any("matcha" in m["fact"].lower() for m in results)


@pytest.mark.anyio
async def test_generate_memories_from_turn(clean_memory_bank):
    """Test asynchronous extraction of memory candidates from athlete dialogue."""
    bank = clean_memory_bank

    turn_input = (
        "Gina mentioned she wants to focus on hip mobility and banded walks before training."
    )
    turn_output = "I have noted your focus and will coordinate with Coach Gor."

    generated = await bank.generate_memories_from_turn(
        turn_input=turn_input,
        turn_output=turn_output,
        persona="ma",
        session_id="session_test_123",
    )

    assert len(generated) >= 1
    new_mem = generated[0]
    assert new_mem["entity"] == "Ma"
    assert new_mem["category"] == "medical_nutrition"
    assert "hip mobility" in new_mem["fact"].lower()


@pytest.mark.anyio
async def test_consolidate_memories_async(clean_memory_bank):
    """Test memory consolidation: deduplicating identical and overlapping facts."""
    bank = clean_memory_bank

    # Add duplicate and near-duplicate entries
    await bank.add_memory_async(
        category="athlete_preferences",
        entity="Gina",
        fact="Prefers oatmeal with blueberries before morning training drills.",
    )
    await bank.add_memory_async(
        category="athlete_preferences",
        entity="Gina",
        fact="Prefers oatmeal with blueberries before morning training drills.",
    )
    await bank.add_memory_async(
        category="athlete_preferences",
        entity="Gina",
        fact="Prefers oatmeal with blueberries before morning training drills.",
    )

    count_before = len(bank._memories)
    summary = await bank.consolidate_memories_async()

    assert summary["initial_count"] == count_before
    assert summary["pruned_count"] >= 1
    assert len(bank._memories) < count_before
    assert summary["timestamp"] is not None


@pytest.mark.anyio
async def test_schedule_memory_generation_non_blocking(clean_memory_bank):
    """Test that scheduling memory generation returns an active task without blocking."""
    bank = clean_memory_bank

    task = bank.schedule_memory_generation(
        turn_input="Sponsor photo shoot with Wilson scheduled between 10:00 AM and 6:00 PM.",
        turn_output="Confirmed the sponsor slot in the team calendar.",
        persona="beita",
        session_id="session_async_test",
    )

    assert task is not None
    assert isinstance(task, asyncio.Task)

    # Await background completion to verify safe execution
    await task
    results = bank.search_memories("Wilson")
    assert any("wilson" in m["fact"].lower() for m in results)


def test_memory_stats(clean_memory_bank):
    """Test retrieval of real-time memory bank statistics."""
    bank = clean_memory_bank
    stats = bank.get_stats()

    assert "total_memories" in stats
    assert stats["total_memories"] >= 5
    assert "categories" in stats
    assert "unconsolidated_count" in stats
    assert "active_background_tasks" in stats
