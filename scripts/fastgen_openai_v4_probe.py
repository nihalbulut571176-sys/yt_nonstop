import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = "https://googler.fast-gen.ai"
STORAGE = "https://storage.fast-gen.ai"
ENV_PATH = Path(r"C:\Users\MIKE\Documents\Codex\YT\.env")
TEMP_DIR = Path(r"C:\Users\MIKE\Documents\Codex\YT\tmp_fastgen_probe")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def load_env_key() -> str:
    if "FAST_GEN_API_KEY" in os.environ and os.environ["FAST_GEN_API_KEY"].strip():
        return os.environ["FAST_GEN_API_KEY"].strip()
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("FAST_GEN_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("FAST_GEN_API_KEY not found")


def request_json(url: str, method: str = "GET", headers=None, data=None):
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read()
        return json.loads(raw.decode("utf-8"))


def upload_test_image(api_key: str) -> str:
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    temp_file = TEMP_DIR / "probe.png"
    temp_file.write_bytes(png_bytes)

    boundary = "----FASTGENBOUNDARY1234567890"
    file_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{temp_file.name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8")
    file_footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = file_header + png_bytes + file_footer

    headers = {
        "X-API-Key": api_key,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    result = request_json(f"{STORAGE}/upload", method="POST", headers=headers, data=body)
    return result["file_hash"]


def try_payload(api_key: str, payload: dict) -> dict:
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8")
    try:
        return {
            "ok": True,
            "payload": payload,
            "response": request_json(
                f"{ROOT}/api/v4/openai/image/generate",
                method="POST",
                headers=headers,
                data=data,
            ),
        }
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = str(e)
        return {
            "ok": False,
            "payload": payload,
            "status": e.code,
            "response": body,
        }


def main() -> None:
    api_key = load_env_key()
    file_hash = upload_test_image(api_key)

    payloads = [
        {
            "prompt": "A realistic portrait of the same person in a business suit",
            "size": "1024x1024",
            "reference_images": [{"image": file_hash, "category": "MEDIA_CATEGORY_SUBJECT"}],
        },
        {
            "prompt": "A realistic portrait of the same person in a business suit",
            "size": "1024x1024",
            "reference_images": [file_hash],
        },
        {
            "prompt": "A realistic portrait of the same person in a business suit",
            "size": "1024x1024",
            "input_image": file_hash,
        },
        {
            "prompt": "A realistic portrait of the same person in a business suit",
            "size": "1024x1024",
            "image": file_hash,
        },
        {
            "prompt": "A realistic portrait of the same person in a business suit",
            "size": "1024x1024",
            "images": [file_hash],
        },
    ]

    results = [try_payload(api_key, payload) for payload in payloads]
    out = TEMP_DIR / "probe_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
