from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Any
import httpx
import hashlib
import time
import json

from backend.logging_config import get_logger

logger = get_logger(__name__)


class RateLimitError(Exception):
    """
    Raised when a provider returns HTTP 429 Too Many Requests.
    Carries the Retry-After value (seconds) from the response header, if present.
    """
    def __init__(self, retry_after: int | None = None, provider: str | None = None):
        self.retry_after = retry_after
        self.provider = provider
        super().__init__(
            f"Rate limit exceeded{f' on {provider}' if provider else ''}"
            f"{f' — retry after {retry_after}s' if retry_after else ''}"
        )


class BaseProvider(ABC):
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @abstractmethod
    async def stream_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        ...


class OpenAICompatProvider(BaseProvider):
    """
    Adapter for all OpenAI-compatible providers (Groq, OpenRouter,
    Gemini OpenAI-compat, Cerebras, NVIDIA NIM, SambaNova, SiliconFlow...).
    """

    async def stream_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # OpenRouter requires these headers for free tier ranking
        if "openrouter" in self.base_url:
            headers["HTTP-Referer"] = "https://nexuslocal.app"
            headers["X-Title"] = "NexusLocal"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        # Some providers/models support reasoning_effort
        # If it's a model that supports thinking (like Mistral's reasoning models or DeepSeek),
        # we can ensure reasoning effort is high if not otherwise configured.
        # But we do not force it unless needed.

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    if response.status_code == 429:
                        retry_after_raw = response.headers.get("Retry-After")
                        retry_after = int(retry_after_raw) if retry_after_raw and retry_after_raw.isdigit() else None
                        raise RateLimitError(retry_after=retry_after, provider=self.base_url)
                    body = await response.aread()
                    detail = body.decode(errors="replace")
                    if response.status_code == 403:
                        raise RuntimeError(
                            "Provider error 403 (access_denied): a chave de API foi rejeitada "
                            "pelo provedor (inválida, expirada, sem saldo/plano ou sem permissão "
                            f"para este modelo). Confira a chave e a conta no console do provedor. "
                            f"Detalhe: {detail}"
                        )
                    raise RuntimeError(
                        f"Provider error {response.status_code}: {detail}"
                    )

                in_thinking = False
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"]
                        
                        # 1. Check for OpenAI/DeepSeek standard `reasoning_content`
                        reasoning_content = delta.get("reasoning_content")
                        content = delta.get("content")

                        # 2. Parse Mistral's or other structured content if it comes as a dict or list
                        # Mistral sometimes sends list of dicts in content chunk:
                        # [{'type': 'thinking', 'thinking': [{'type': 'text', 'text': '...'}]}]
                        structured_thinking = ""
                        structured_text = ""
                        
                        if content is not None:
                            # Content can be a string, a list, or a dict depending on the model's output
                            if isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict):
                                        item_type = item.get("type")
                                        if item_type == "thinking":
                                            # It can contain a nested list of text items
                                            nested = item.get("thinking", [])
                                            if isinstance(nested, list):
                                                for n in nested:
                                                    if isinstance(n, dict) and n.get("type") == "text":
                                                        structured_thinking += n.get("text", "")
                                            elif isinstance(nested, str):
                                                structured_thinking += nested
                                        elif item_type == "text":
                                            structured_text += item.get("text", "")
                            elif isinstance(content, dict):
                                item_type = content.get("type")
                                if item_type == "thinking":
                                    nested = content.get("thinking", [])
                                    if isinstance(nested, list):
                                        for n in nested:
                                            if isinstance(n, dict) and n.get("type") == "text":
                                                structured_thinking += n.get("text", "")
                                    elif isinstance(nested, str):
                                        structured_thinking += nested
                                elif item_type == "text":
                                    structured_text += content.get("text", "")
                            elif isinstance(content, str):
                                # It could be a string representation of a JSON list/dict because of parsing issues
                                content_stripped = content.strip()
                                if (content_stripped.startswith("[") and content_stripped.endswith("]")) or (content_stripped.startswith("{") and content_stripped.endswith("}")):
                                    try:
                                        # Replace single quotes with double quotes to make it valid JSON if needed
                                        # (Mistral sometimes prints python repr in ollama/some backends, or actual JSON string)
                                        normalized_json = content_stripped.replace("'", '"')
                                        parsed_content = json.loads(normalized_json)
                                        if isinstance(parsed_content, list):
                                            for item in parsed_content:
                                                if isinstance(item, dict):
                                                    item_type = item.get("type")
                                                    if item_type == "thinking":
                                                        nested = item.get("thinking", [])
                                                        if isinstance(nested, list):
                                                            for n in nested:
                                                                if isinstance(n, dict) and n.get("type") == "text":
                                                                    structured_thinking += n.get("text", "")
                                                        elif isinstance(nested, str):
                                                            structured_thinking += nested
                                                    elif item_type == "text":
                                                        structured_text += item.get("text", "")
                                        elif isinstance(parsed_content, dict):
                                            item_type = parsed_content.get("type")
                                            if item_type == "thinking":
                                                nested = parsed_content.get("thinking", [])
                                                if isinstance(nested, list):
                                                    for n in nested:
                                                        if isinstance(n, dict) and n.get("type") == "text":
                                                            structured_thinking += n.get("text", "")
                                                elif isinstance(nested, str):
                                                                structured_thinking += nested
                                            elif item_type == "text":
                                                structured_text += parsed_content.get("text", "")
                                    except Exception:
                                        pass

                        # If we extracted structured content, override content/reasoning_content variables
                        if structured_thinking:
                            reasoning_content = (reasoning_content or "") + structured_thinking
                        if structured_text:
                            content = structured_text

                        # If both or either are present, format them
                        chunk_to_yield = ""
                        
                        if reasoning_content:
                            if not in_thinking:
                                chunk_to_yield += "<think>"
                                in_thinking = True
                            chunk_to_yield += reasoning_content
                        
                        if content:
                            if in_thinking:
                                chunk_to_yield += "</think>"
                                in_thinking = False
                            chunk_to_yield += content
                            
                        if chunk_to_yield:
                            yield chunk_to_yield

                    except Exception:
                        continue

                # Close thinking tag if it was left open
                if in_thinking:
                    yield "</think>"


class CloudflareProvider(BaseProvider):
    """
    Native Cloudflare Workers AI provider.
    Uses the REST endpoint: POST /accounts/{account_id}/ai/run/{model}
    instead of the OpenAI-compatible /v1/chat/completions endpoint.

    The base_url is expected to be:
      https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1
    We extract the account_id and build the correct /ai/run/ URL.
    """

    def _run_url(self, model: str) -> str:
        # Extract account_id from the base_url
        # base_url format: https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1
        import re
        m = re.search(r"/accounts/([^/]+)/ai", self.base_url)
        if m:
            account_id = m.group(1)
        else:
            # fallback: treat base_url as the accounts prefix
            account_id = "unknown"
        return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"

    async def stream_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Filter out 'system' messages for models that don't support them,
        # merging them into the first user message if needed.
        filtered = []
        system_text = ""
        for msg in messages:
            if msg["role"] == "system":
                system_text += msg["content"] + "\n"
            else:
                filtered.append(msg)
        # Prepend system content to first user message if present
        if system_text and filtered:
            filtered[0] = {
                "role": filtered[0]["role"],
                "content": system_text.strip() + "\n\n" + filtered[0]["content"],
            }
        elif system_text:
            filtered = [{"role": "user", "content": system_text.strip()}]

        payload = {
            "messages": filtered,
            "stream": True,
            "max_tokens": max_tokens,
        }

        url = self._run_url(model)

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    if response.status_code == 429:
                        retry_after_raw = response.headers.get("Retry-After")
                        retry_after = int(retry_after_raw) if retry_after_raw and retry_after_raw.isdigit() else None
                        raise RateLimitError(retry_after=retry_after, provider="cloudflare")
                    body = await response.aread()
                    raise RuntimeError(
                        f"Provider error {response.status_code}: {body.decode()}"
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        # Native CF format: {"response": "token"}
                        response_text = chunk.get("response")
                        if response_text is not None and response_text != "":
                            yield str(response_text)
                        # Also handle OpenAI-compat format in case CF returns it
                        elif "choices" in chunk:
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content")
                            if content is not None and content != "":
                                yield str(content)
                    except Exception:
                        continue


# Global cache directory for Gemini context caches: hash -> (cache_id, expire_time)
GEMINI_CACHE: Dict[str, tuple] = {}


class GeminiProvider(BaseProvider):
    """
    Native Gemini API Provider with Context Caching.
    If the context is large (>= 130,000 chars, approx 32k tokens), it creates
    and uses a Google Context Cache. Otherwise, it falls back to the OpenAI-compat endpoint.
    """

    async def stream_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        # Estimate total character length to check if we should attempt caching
        # Context caching has a minimum token limit of 32,768 tokens (approx 130,000 characters)
        has_multimodal = any(isinstance(m.get("content"), list) for m in messages)
        total_chars = 0 if has_multimodal else sum(len(m.get("content", "")) for m in messages)

        # Prepare headers for Gemini Native API
        headers = {
            "Content-Type": "application/json"
        }
        if self.api_key.startswith("AIzaSy"):
            headers["x-goog-api-key"] = self.api_key
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # We need a specific model ID format for caching, e.g. "models/gemini-1.5-flash"
        model_name = model
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"

        # Caching is only viable if there's history to cache (more than 1 message) and total content is large
        if not has_multimodal and len(messages) > 1 and total_chars >= 130000:
            try:
                # Caching prefix includes all messages except the last user query
                prefix_messages = messages[:-1]

                # Format prefix messages to Gemini REST API format
                gemini_contents = []
                system_instruction = None

                for msg in prefix_messages:
                    role = msg["role"]
                    content = msg["content"]
                    if role == "system":
                        system_instruction = {
                            "parts": [{"text": content}]
                        }
                    else:
                        gemini_contents.append({
                            "role": "user" if role == "user" else "model",
                            "parts": [{"text": content}]
                        })

                # Create hash of prefix to identify cached contents
                prefix_str = json.dumps(prefix_messages, sort_keys=True)
                prefix_hash = hashlib.sha256(prefix_str.encode()).hexdigest()

                cache_id = None
                now = time.time()

                # Check if we already have a valid active cache
                if prefix_hash in GEMINI_CACHE:
                    cid, expire = GEMINI_CACHE[prefix_hash]
                    if expire > now + 30:  # 30s grace period
                        cache_id = cid

                if not cache_id:
                    # Create cached content
                    cache_payload = {
                        "model": model_name,
                        "contents": gemini_contents,
                        "ttl": "600s"  # 10 minutes cache TTL
                    }
                    if system_instruction:
                        cache_payload["systemInstruction"] = system_instruction

                    async with httpx.AsyncClient(timeout=30.0) as client:
                        r = await client.post(
                            "https://generativelanguage.googleapis.com/v1beta/cachedContents",
                            headers=headers,
                            json=cache_payload
                        )
                        if r.status_code == 200:
                            res_data = r.json()
                            cache_id = res_data["name"]
                            expire_str = res_data.get("expireTime", "")
                            if expire_str:
                                try:
                                    from datetime import datetime

                                    dt = datetime.strptime(expire_str.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
                                    expire_epoch = dt.timestamp()
                                    GEMINI_CACHE[prefix_hash] = (cache_id, expire_epoch)
                                except Exception:
                                    GEMINI_CACHE[prefix_hash] = (cache_id, now + 600)
                            else:
                                GEMINI_CACHE[prefix_hash] = (cache_id, now + 600)
                            logger.info("✅ Gemini Context Cache criado com sucesso: %s", cache_id)

                if cache_id:
                    # Cache exists! Stream using the cache
                    last_msg = messages[-1]
                    last_gemini_content = [{
                        "role": "user" if last_msg["role"] == "user" else "model",
                        "parts": [{"text": last_msg["content"]}]
                    }]

                    payload = {
                        "contents": last_gemini_content,
                        "cachedContent": cache_id,
                        "generationConfig": {
                            "temperature": temperature,
                            "maxOutputTokens": max_tokens
                        }
                    }

                    # Call streamGenerateContent
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        async with client.stream(
                            "POST",
                            f"https://generativelanguage.googleapis.com/v1beta/{model_name}:streamGenerateContent?alt=sse",
                            headers=headers,
                            json=payload
                        ) as response:
                            if response.status_code == 200:
                                async for line in response.aiter_lines():
                                    if not line.startswith("data: "):
                                        continue
                                    data = line[6:]
                                    try:
                                        chunk = json.loads(data)
                                        part = chunk["candidates"][0]["content"]["parts"][0]
                                        text = part.get("text")
                                        if text is not None and text != "":
                                            yield str(text)
                                    except Exception:
                                        continue
                                return  # Stream finished successfully!
                            else:
                                logger.error("Gemini cached stream failed (%s), falling back to OpenAICompat...", response.status_code)
            except Exception as e:
                logger.error("Error implementing Gemini Context Caching: %s. Falling back to OpenAICompat...", exc_info=e)

        # Fallback to Native Gemini API if it is an AI Studio key (starts with AIzaSy or AQ.)
        is_ai_studio_key = self.api_key.startswith("AIzaSy") or self.api_key.startswith("AQ.")
        if is_ai_studio_key:
            try:
                # Convert OpenAI messages structure to Gemini native contents
                gemini_contents = []
                system_instruction = None
                
                for msg in messages:
                    role = msg["role"]
                    content = msg["content"]
                    
                    if role == "system":
                        if isinstance(content, str):
                            system_instruction = {"parts": [{"text": content}]}
                        elif isinstance(content, list):
                            parts = []
                            for part in content:
                                if part.get("type") == "text":
                                    parts.append({"text": part["text"]})
                            system_instruction = {"parts": parts}
                    else:
                        parts = []
                        if isinstance(content, str):
                            parts.append({"text": content})
                        elif isinstance(content, list):
                            for part in content:
                                if part.get("type") == "text":
                                    parts.append({"text": part["text"]})
                                elif part.get("type") == "image_url":
                                    img_url = part["image_url"]["url"]
                                    if img_url.startswith("data:"):
                                        try:
                                            header, base64_data = img_url.split(";base64,")
                                            mime_type = header.replace("data:", "")
                                            parts.append({
                                                "inlineData": {
                                                    "mimeType": mime_type,
                                                    "data": base64_data
                                                }
                                            })
                                        except Exception as e:
                                            logger.error("[Gemini Native] Error parsing base64 image:", exc_info=e)
                        
                        gemini_contents.append({
                            "role": "user" if role == "user" else "model",
                            "parts": parts
                        })

                payload = {
                    "contents": gemini_contents,
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens
                    }
                }
                if system_instruction:
                    payload["systemInstruction"] = system_instruction

                # AQ. = OAuth2 access token → Authorization: Bearer header (no ?key=)
                # AIzaSy = standard API key → ?key= URL param (no auth header)
                if self.api_key.startswith("AQ."):
                    native_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:streamGenerateContent?alt=sse"
                    native_headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    }
                else:
                    native_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:streamGenerateContent?alt=sse&key={self.api_key}"
                    native_headers = {"Content-Type": "application/json"}
                
                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream(
                        "POST",
                        native_url,
                        headers=native_headers,
                        json=payload
                    ) as response:
                        if response.status_code == 200:
                            async for line in response.aiter_lines():
                                if not line.startswith("data: "):
                                    continue
                                data = line[6:]
                                try:
                                    chunk = json.loads(data)
                                    part = chunk["candidates"][0]["content"]["parts"][0]
                                    text = part.get("text")
                                    if text is not None and text != "":
                                        yield str(text)
                                except Exception:
                                    continue
                            return  # Stream finished successfully!
                        else:
                            if response.status_code == 429:
                                retry_after_raw = response.headers.get("Retry-After")
                                retry_after = int(retry_after_raw) if retry_after_raw and retry_after_raw.isdigit() else None
                                raise RateLimitError(retry_after=retry_after, provider="gemini")
                            body = await response.aread()
                            err = f"[Gemini Native] API error {response.status_code}: {body.decode()}"
                            logger.info(err)
                            raise RuntimeError(err)
            except (RuntimeError, RateLimitError):
                raise  # Propagate API errors upward — do NOT swallow into OpenAICompat
            except Exception as e:
                logger.error("[Gemini Native Error] %s. Falling back to OpenAICompat...", exc_info=e)

        # FALLBACK: Use standard OpenAICompatProvider logic
        openai_provider = OpenAICompatProvider(api_key=self.api_key, base_url=self.base_url)
        async for chunk in openai_provider.stream_chat(model, messages, temperature, max_tokens):
            yield chunk
