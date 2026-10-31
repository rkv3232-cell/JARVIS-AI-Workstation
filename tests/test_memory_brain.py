import pytest
from backend.memory.memory_brain import PersistentMemoryBrain, MemoryCategory

def test_persistent_memory_crud_and_fts():
    # 1. Add Memory
    mem_id = PersistentMemoryBrain.add_memory(
        category=MemoryCategory.USER_PREFERENCES,
        content="User prefers 15-minute timeframe and SMC order blocks on NIFTY50.",
        key="trading_timeframe",
        tags=["trading", "smc", "nifty"]
    )
    assert mem_id.startswith("mem_")

    # 2. Get Memories
    mems = PersistentMemoryBrain.get_memories(category=MemoryCategory.USER_PREFERENCES)
    found = any(m["id"] == mem_id for m in mems)
    assert found is True

    # 3. Search via FTS5
    search_res = PersistentMemoryBrain.search_memories("SMC order blocks")
    assert len(search_res) > 0
    assert any(m["id"] == mem_id for m in search_res)

    # 4. Update Memory
    up_ok = PersistentMemoryBrain.update_memory(mem_id, "Updated preference to 5-minute timeframe.")
    assert up_ok is True

    # 5. Delete Memory
    del_ok = PersistentMemoryBrain.delete_memory(mem_id)
    assert del_ok is True

def test_memory_export_and_import():
    # Add a memory to export
    mid = PersistentMemoryBrain.add_memory(
        category=MemoryCategory.PROJECT_MEMORY,
        content="JARVIS-APEX Windows Architecture v2.1"
    )
    backup = PersistentMemoryBrain.export_all_memories()
    assert "memories" in backup
    assert backup["total_memories"] > 0

    # Test import
    imported_count = PersistentMemoryBrain.import_memories(backup)
    assert imported_count > 0

    PersistentMemoryBrain.delete_memory(mid)

def test_research_jobs_persistence():
    job_id = PersistentMemoryBrain.create_research_job("Quantum Computing", mode="DEEP")
    assert job_id.startswith("res_")

    job = PersistentMemoryBrain.get_research_job(job_id)
    assert job is not None
    assert job["topic"] == "Quantum Computing"
    assert job["status"] == "PENDING"

    # Update progress
    PersistentMemoryBrain.update_research_job(
        job_id,
        progress=50,
        step="Multi-source fact extraction",
        status="RUNNING"
    )
    updated_job = PersistentMemoryBrain.get_research_job(job_id)
    assert updated_job["progress"] == 50
    assert updated_job["status"] == "RUNNING"
