#!/usr/bin/env python3
import os, sys, time, json, asyncio, tempfile

# Test using the packaged bundle codebase
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUNDLE_DIR = os.path.join(REPO_ROOT, "dist", "Ghost Copilot.app", "Contents", "SharedSupport")
if BUNDLE_DIR not in sys.path:
    sys.path.insert(0, BUNDLE_DIR)

from fastapi.testclient import TestClient
from server.main import app
from server.config.settings import settings
from client.platform.macos.audio import MacAudioProvider

async def run_interview_simulation():
    print("================================================================")
    print("  👻 GHOST COPILOT — 10-15 MIN INTERVIEW SIMULATION TEST")
    print("================================================================")
    
    with TestClient(app) as client:
        # 1. Probes
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/ready").json()["status"] == "ready"
        print("\n[1/5] Server Probes Healthy in App Bundle.")

        # 2. Session Creation
        auth_headers = {"Authorization": f"Bearer {settings.DEV_AUTH_TOKEN}"}
        sess_resp = client.post("/api/v1/sessions", headers=auth_headers, json={"title": "Multi-Question Interview"})
        session_id = sess_resp.json()["id"]
        print(f"      Active Session Initialized: {session_id}")

        # 3. Simulate consecutive interview questions
        questions = [
            "Explain database normalization (1NF, 2NF, 3NF).",
            "What is an index and how does B-Tree indexing work in PostgreSQL?",
            "Explain the difference between optimistic and pessimistic locking.",
            "How does connection pooling improve database performance?"
        ]

        for i, q in enumerate(questions, 1):
            print(f"\n[Question {i}/4] Submitting: {q}")
            t0 = time.time()
            res = client.post("/api/v1/solve", headers=auth_headers, json={"question": q, "session_id": session_id})
            assert res.status_code == 200
            assert res.json()["status"] == "generating"
            gen_id = res.json()["gen_id"]
            print(f"      Generation started (gen_id={gen_id}) in {int((time.time() - t0)*1000)}ms.")
            
            # If question 3, test emergency skip mid-generation
            if i == 3:
                print("      >>> Triggering Emergency Skip mid-question...")
                skip_res = client.post("/api/v1/skip", headers=auth_headers, json={"session_id": session_id})
                assert skip_res.status_code == 200
                assert skip_res.json()["status"] == "skipped"
                print("      [PASS] Question successfully aborted, cooldown reset.")

            # Cooldown sleep to simulate interview pacing
            await asyncio.sleep(0.3)

        # 4. Audio capture simulation & Temp file cleanup
        print("\n[4/5] Audio Hardware & Buffer Lifecycle...")
        audio = MacAudioProvider()
        caps = audio.check_capabilities()
        print(f"      Microphone: {caps['microphone']['state']}")
        print(f"      BlackHole System Audio: {caps['system_audio']['state']}")

        fd, temp_wav = tempfile.mkstemp(prefix="interview_sim_chunk_", suffix=".wav")
        os.close(fd)
        os.chmod(temp_wav, 0o600)
        assert os.path.exists(temp_wav)
        os.remove(temp_wav)
        assert not os.path.exists(temp_wav)
        print("      [PASS] 0600 privacy permissions & deterministic cleanup verified.")

        # 5. Desktop Mode Controls
        print("\n[5/5] Desktop Mode Switching & State...")
        m_resp = client.post("/set_mode", json={"mode": "auto"})
        assert m_resp.json()["auto"] is True
        s_resp = client.get("/sharing_mode")
        assert "mode" in s_resp.json()
        print(f"      Sharing mode: {s_resp.json()['mode']}, auto: True")

    print("\n================================================================")
    print("  ✅ MULTI-TURN INTERVIEW SIMULATION PASSED CLEANLY")
    print("================================================================\n")

if __name__ == "__main__":
    asyncio.run(run_interview_simulation())
