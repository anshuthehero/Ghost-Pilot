"""
Async Groq AI Provider Client for Ghost Copilot.
Handles Whisper Audio Transcription and Streaming Chat Completions.
"""

import json
import os
import urllib.request
import asyncio
from typing import AsyncGenerator, List, Dict, Any, Optional
from server.config.settings import settings

WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

BASE_SYSTEM_PROMPT = """You are a brilliant real-time interview assistant. Answer ANY question — technical, general knowledge, HR, behavioural, domain-specific.

RULES:
- Answer directly. No preamble, no filler phrases.
- Factual/general knowledge (capitals, dates, definitions): 1-2 sentences max.
- Technical questions: key concept + 2-3 crisp bullet points.
- HR/behavioural: structured, natural-sounding answer using STAR framework where appropriate.
- No code blocks unless explicitly asked.
- Be authoritative. Never say "I think" or "I believe" for facts."""


class GroqClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.AI_API_KEY or settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.whisper_model = settings.GROQ_WHISPER_MODEL

    async def transcribe_audio_file(self, audio_path: str) -> Optional[str]:
        """
        Transcribes an audio file via Groq Whisper API asynchronously.
        Does not block the main event loop.
        """
        if not self.api_key:
            return None
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 4000:
            return None

        # Build multipart curl/subprocess or native request in executor
        def _sync_transcribe():
            import subprocess
            import shutil
            import urllib.request
            import secrets

            curl_bin = shutil.which("curl") or ("/usr/bin/curl" if os.path.exists("/usr/bin/curl") else None)
            if curl_bin:
                safe_audio_path = audio_path.replace("\\", "/")
                cmd = [
                    curl_bin, "-s", WHISPER_URL,
                    "-H", f"Authorization: Bearer {self.api_key}",
                    "-F", f"file=@{safe_audio_path}",
                    "-F", f"model={self.whisper_model}",
                    "-F", "language=en"
                ]
                sp_kwargs = {"timeout": 10}
                if sys.platform.startswith("win"):
                    sp_kwargs["creationflags"] = 0x08000000
                try:
                    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, **sp_kwargs)
                    if r.stdout:
                        data = json.loads(r.stdout)
                        return data.get("text", "").strip()
                except Exception:
                    pass

            # Pure Python fallback
            try:
                boundary = f"----GhostCopilot{secrets.token_hex(12)}"
                filename = os.path.basename(audio_path)
                with open(audio_path, "rb") as f:
                    file_bytes = f.read()

                parts = [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
                    b"Content-Type: audio/wav\r\n\r\n",
                    file_bytes,
                    b"\r\n",
                    f"--{boundary}\r\n".encode(),
                    b'Content-Disposition: form-data; name="model"\r\n\r\n',
                    f"{self.whisper_model}\r\n".encode(),
                    f"--{boundary}\r\n".encode(),
                    b'Content-Disposition: form-data; name="language"\r\n\r\n',
                    b"en\r\n",
                    f"--{boundary}--\r\n".encode()
                ]
                payload = b"".join(parts)
                req = urllib.request.Request(
                    WHISPER_URL,
                    data=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                        "User-Agent": "GhostCopilot/3.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode())
                    return data.get("text", "").strip()
            except Exception:
                return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync_transcribe)

    async def stream_chat_completion(
        self,
        question: str,
        history: Optional[List[Dict[str, str]]] = None,
        custom_instructions: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streams chat completion tokens from Groq as an async generator.
        """
        if not self.api_key:
            yield "[Warning] GROQ_API_KEY is not configured on the server."
            return

        system_content = BASE_SYSTEM_PROMPT
        if custom_instructions:
            system_content += f"\n\nADDITIONAL USER INSTRUCTIONS:\n{custom_instructions}"

        messages = [{"role": "system", "content": system_content}]
        if history:
            messages.extend(history[-6:])  # Include up to last 6 turns
        messages.append({"role": "user", "content": question})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 400,
            "stream": True
        }

        # Run the streaming HTTP request in an async generator
        queue: asyncio.Queue = asyncio.Queue()

        def _sync_stream():
            req = urllib.request.Request(
                CHAT_URL,
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "GhostCopilot-Server/3.0"
                }
            )
            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    for line in resp:
                        line = line.decode().strip()
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                        try:
                            token = json.loads(line[6:])["choices"][0]["delta"].get("content", "")
                            if token:
                                asyncio.run_coroutine_threadsafe(queue.put(token), loop)
                        except Exception:
                            continue
            except Exception as e:
                asyncio.run_coroutine_threadsafe(queue.put(Exception(f"AI Provider Error: {str(e)}")), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _sync_stream)

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                yield f"\n\n[Error] {item}"
                break
            yield item


ai_client = GroqClient()
