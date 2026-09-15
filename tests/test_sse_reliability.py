"""
Tests for Server-Sent Events (SSE) Reliability and Multi-Tenant Stream Isolation.
Verifies concurrent stream delivery, client connect/disconnect, and zero cross-talk between users.
"""

import asyncio
import pytest
from server.sessions.manager import SessionManager, SessionContext


@pytest.mark.asyncio
async def test_concurrent_sessions_receive_only_their_own_events():
    """Proves User A and User B concurrently streaming never receive each other's events."""
    manager = SessionManager()

    # Create session contexts for User A and User B
    ctx_a = await manager.get_or_create_context("session-alpha", "user-1")
    ctx_b = await manager.get_or_create_context("session-beta", "user-2")

    # Connect client subscriber queues
    q_a = ctx_a.add_subscriber()
    q_b = ctx_b.add_subscriber()

    # Emit distinct tokens concurrently
    await asyncio.gather(
        ctx_a.broadcast("token", {"text": "Alpha Token 1"}),
        ctx_b.broadcast("token", {"text": "Beta Token 1"}),
        ctx_a.broadcast("token", {"text": "Alpha Token 2"}),
        ctx_b.broadcast("token", {"text": "Beta Token 2"}),
    )

    # Read events from Queue A
    events_a = []
    while not q_a.empty():
        events_a.append(await q_a.get())

    # Read events from Queue B
    events_b = []
    while not q_b.empty():
        events_b.append(await q_b.get())

    # Verify Queue A has ONLY Alpha events
    assert len(events_a) == 2
    assert all("Alpha" in ev["data"]["text"] for ev in events_a)
    assert not any("Beta" in ev["data"]["text"] for ev in events_a)

    # Verify Queue B has ONLY Beta events
    assert len(events_b) == 2
    assert all("Beta" in ev["data"]["text"] for ev in events_b)
    assert not any("Alpha" in ev["data"]["text"] for ev in events_b)


@pytest.mark.asyncio
async def test_sse_client_disconnect_and_reconnect():
    """Verifies that disconnecting a subscriber cleans up memory and reconnecting works cleanly."""
    ctx = SessionContext("session-disconnect-test", "user-1")
    
    # 1. Connect first client
    q1 = ctx.add_subscriber()
    assert len(ctx.subscribers) == 1

    # 2. Disconnect client
    ctx.remove_subscriber(q1)
    assert len(ctx.subscribers) == 0

    # 3. Broadcasting to empty subscriber list succeeds silently without error
    await ctx.broadcast("ping", {"status": "heartbeat"})

    # 4. Reconnect new client
    q2 = ctx.add_subscriber()
    assert len(ctx.subscribers) == 1

    await ctx.broadcast("answer_start", {"question": "Hello"})
    ev = await q2.get()
    assert ev["event"] == "answer_start"
    assert ev["data"]["question"] == "Hello"


@pytest.mark.asyncio
async def test_duplicate_connections_to_same_session():
    """Validates that multiple browser/HUD windows for the same user session all receive broadcasts."""
    ctx = SessionContext("session-multi-window", "user-1")
    
    q_hud = ctx.add_subscriber()
    q_browser = ctx.add_subscriber()
    assert len(ctx.subscribers) == 2

    await ctx.broadcast("token", {"text": "Shared Token"})

    ev1 = await q_hud.get()
    ev2 = await q_browser.get()

    assert ev1["data"]["text"] == "Shared Token"
    assert ev2["data"]["text"] == "Shared Token"


@pytest.mark.asyncio
async def test_session_abort_isolation():
    """Aborting User A's generation must not interfere with User B's active generation ID."""
    manager = SessionManager()
    ctx_a = await manager.get_or_create_context("sess-1", "user-1")
    ctx_b = await manager.get_or_create_context("sess-2", "user-2")

    initial_gen_b = ctx_b.active_gen_id
    ctx_a.abort_current_generation()

    assert ctx_a.active_gen_id == 1
    assert ctx_b.active_gen_id == initial_gen_b
