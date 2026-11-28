"""Nối model — chỗ DUY NHẤT trong bản chạy thử gọi model AI. NHÓM VIẾT phần gọi model thật.

Hợp đồng (giữ nguyên để khung đo được token):
    call_model(system: str, user: str) -> dict với 4 khoá
        "text":       str   chữ model trả về
        "model":      str   tên model đã gọi (để tra giá ở bảng giá model)
        "tokens_in":  int   số token vào, lấy từ trường usage trong phản hồi API — KHÔNG ước lượng
        "tokens_out": int   số token ra, gồm cả token suy luận / suy nghĩ nếu API tính riêng
    @model_call (từ tracing.py) tự ghi mỗi lần gọi vào trace; agent.py gọi call_model bao nhiêu lần
    cũng được, khung tự cộng token.
    Lỗi gọi model (hết lượt, sai key, mất mạng): cứ để exception bay ra — khung ghi lỗi vào cột error.

Chế độ giả (mặc định khi .env chưa có MODEL_PROVIDER, hoặc MODEL_PROVIDER=fake):
    trả một câu giả cố định, model "fake", token 0 — để luồng chạy hết từ trước CP2 (guide bước 3.2).
    Lượt `run.py eval` / `run.py simulate` chạy bằng model giả KHÔNG được tính.

Nối model thật: điền .env (chép từ .env.example), rồi viết nhánh gọi API ở dưới theo docs/connect-model.md
(có ví dụ OpenAI, Claude, model chạy trên máy, và cách nối nhà cung cấp khác). Không dán API key vào file này.
"""
import atexit
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

if __package__:
    from .tracing import model_call
else:
    from tracing import model_call

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=os.path.join(ROOT, ".env")):
    """Đọc file .env (KEY=VALUE mỗi dòng) vào biến môi trường, không ghi đè biến đã có. Khung — không cần sửa."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
MODEL_PROVIDER = (os.environ.get("MODEL_PROVIDER") or "fake").strip().lower()
MODEL_NAME = (os.environ.get("MODEL_NAME") or "").strip()
API_KEY = (os.environ.get("API_KEY") or "").strip()


def llama_model_paths():
    paths = {}
    missing = []
    for key in ("LLAMACPPPATH", "GGUFPath"):
        value = os.environ.get(key, "")
        path = Path(ROOT) / Path(os.path.expandvars(value)).expanduser()
        if not value or not path.is_file() or (key == "GGUFPath" and path.suffix.lower() != ".gguf"):
            missing.append(key)
        elif key == "LLAMACPPPATH" and not os.access(path, os.X_OK):
            missing.append(key)
        else:
            paths[key] = path.resolve()
    if missing:
        raise ValueError("Không tìm thấy tệp hợp lệ. Kiểm tra trong .env: " + ", ".join(missing))
    return paths["LLAMACPPPATH"], paths["GGUFPath"]


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_ready(process, port):
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ValueError(f"llama-server dừng khi khởi động (mã {process.returncode}). Kiểm tra GGUF và llama-server.")
        try:
            with opener.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                if response.status == 200 and process.poll() is None:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.5)
    raise ValueError("llama-server chưa sẵn sàng sau 120 giây.")


def _stop_server(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@contextmanager
def llama_server(executable, model):
    port = _free_port()
    command = [
        str(executable), "-m", str(model), "--alias", "local-model",
        "--host", "127.0.0.1", "--port", str(port), "-ngl", "99",
        "-t", "4", "-tb", "4", "-np", "1", "-c", "8192",
    ]
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise ValueError("Không chạy được llama-server. Kiểm tra LLAMACPPPATH và quyền thực thi.") from exc
    def cleanup():
        _stop_server(process)

    atexit.register(cleanup)
    try:
        _wait_ready(process, port)
        yield port
    except URLError as exc:
        if process.poll() is not None:
            raise ValueError(f"llama-server đã dừng trong khi trích xuất (mã {process.returncode}).") from exc
        raise
    finally:
        cleanup()
        atexit.unregister(cleanup)


class _LocalOnly(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ModelResponseTruncated(ValueError):
    """The model reached its generation limit before completing the response."""


class ModelInputTooLarge(ValueError):
    """The prompt exceeds the server's available context."""


def _llama_http_error(error):
    with error:
        body = error.read(8192).lower()
    if error.code in {400, 413} and (
        error.code == 413 or b"exceed_context_size" in body
        or (b"context" in body and any(word in body for word in (b"exceed", b"too large", b"too long")))
    ):
        return ModelInputTooLarge("Dữ liệu gửi tới llama-server vượt cửa sổ ngữ cảnh.")
    if error.code in {401, 403}:
        return ValueError(f"llama-server từ chối xác thực (HTTP {error.code}). Kiểm tra LLAMA_API_KEY.")
    return ValueError(f"llama-server trả lỗi HTTP {error.code} khi trích xuất.")


def _read_llama_stream(response, stats):
    content = []
    result = {}
    choice = {}
    live_prompt = 0
    for line in response:
        if not line.startswith(b"data:"):
            continue
        payload = line[5:].strip()
        if payload == b"[DONE]":
            break
        chunk = json.loads(payload)
        if "error" in chunk:
            raise ValueError("llama-server báo lỗi khi tạo phản hồi.")
        if chunk.get("model"):
            result["model"] = chunk["model"]
        if chunk.get("usage"):
            result["usage"] = chunk["usage"]
        if options := chunk.get("choices"):
            part = options[0]
            if text := part.get("delta", {}).get("content"):
                content.append(text)
            if part.get("finish_reason"):
                choice["finish_reason"] = part["finish_reason"]
        if prompt := chunk.get("prompt_progress"):
            live_prompt = prompt.get("total", live_prompt)
        if timings := chunk.get("timings"):
            result["timings"] = timings
        if prompt or timings:
            current = result.get("timings", {})
            stats(live_prompt, current.get("predicted_n", 0), current.get("predicted_per_second"), False)
    if "finish_reason" not in choice:
        raise ValueError("llama-server ngắt luồng trước khi hoàn tất phản hồi.")
    choice["message"] = {"content": "".join(content)}
    result["choices"] = [choice]
    return result


def _llama_completion(system, user, port, model, timeout, schema, stats=None):
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 4096,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if schema is not None:
        body["response_format"] = {"type": "json_object", "schema": schema}
    if stats is not None:
        body.update(stream=True, stream_options={"include_usage": True},
                    timings_per_token=True, return_progress=True)
        stats(0, 0, None, False)
    headers = {"Content-Type": "application/json"}
    if api_key := os.environ.get("LLAMA_API_KEY"):
        headers["Authorization"] = "Bearer " + api_key
    request = Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        json.dumps(body, ensure_ascii=False).encode("utf-8"), headers,
    )
    opener = build_opener(ProxyHandler({}), _LocalOnly())
    try:
        with opener.open(request, timeout=timeout) as response:
            if stats is not None and response.headers.get_content_type() == "text/event-stream":
                result = _read_llama_stream(response, stats)
            else:
                result = json.load(response)
    except HTTPError as exc:
        raise _llama_http_error(exc) from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise exc.reason from exc
        raise
    choice = result["choices"][0]
    usage = result.get("usage")
    if stats is not None and usage is not None:
        stats(usage["prompt_tokens"], usage["completion_tokens"],
              result.get("timings", {}).get("predicted_per_second"), True)
    if choice.get("finish_reason") == "length":
        raise ModelResponseTruncated("llama-server reached its response token limit.")
    if usage is None:
        raise ValueError("llama-server không trả số token cho phản hồi.")
    return {
        "text": choice["message"]["content"],
        "model": result.get("model") or model,
        "tokens_in": usage["prompt_tokens"],
        "tokens_out": usage["completion_tokens"],
    }



@model_call
def call_model(system: str, user: str, *, llama_port=None, model=None, timeout=600, schema=None, stats=None) -> dict:
    if llama_port is not None:
        return _llama_completion(system, user, llama_port, model or "local-model", timeout, schema, stats)
    if MODEL_PROVIDER == "llamacpp":
        port = int(os.environ.get("LLAMA_PORT", "8080"))
        return _llama_completion(system, user, port, model or MODEL_NAME or "local-model", timeout, schema, stats)
    if MODEL_PROVIDER == "fake":
        last = (user.strip().splitlines() or [""])[-1]
        return {"text": "[câu trả lời giả — chưa nối model] " + last[:60], "model": "fake", "tokens_in": 0, "tokens_out": 0}

    # NHÓM VIẾT: gọi model thật ở đây (theo MODEL_PROVIDER, MODEL_NAME, API_KEY) rồi trả đúng 4 khoá.
    # Ví dụ chép được cho từng nhà cung cấp: docs/connect-model.md mục 2.
    raise NotImplementedError(
        "chưa viết phần gọi model thật cho MODEL_PROVIDER=%s trong codebase/ai.py — xem docs/connect-model.md"
        % MODEL_PROVIDER)
