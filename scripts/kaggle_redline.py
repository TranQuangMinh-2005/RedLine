# =====================================================================
#  RedLine RAG Agent trên Kaggle T4 x2 — Ollama + FastAPI + ngrok
#  One-shot: Clone repo -> Cài đặt Ollama (CUDA) -> Tải Qwen2.5-14B ->
#            Seed Mock DB -> Ingest RAG -> Chạy Target -> Expose ngrok
#
#     - Model LLM     : qwen2.5:14b (Q4_K_M ~9 GB, tối ưu 2x T4 16GB, native tool calling)
#     - Target Server : FastAPI trên cổng 8000 (endpoints: /health, /chat)
#     - RAG Knowledge : 14 tài liệu chính sách mock trong data/rag/documents/
#     - Mock Database : SQLite sandbox (customers, orders, tickets)
#     - API Public    : qua ngrok (cần NGROK_AUTH_TOKEN trong Kaggle Secrets)
#
#  Dán toàn bộ file này vào 1 cell của Kaggle Notebook rồi Run.
#  Trước khi chạy: Settings -> Accelerator = GPU T4 x2, Internet = ON
# =====================================================================
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request

# ============================== CONFIG ===============================
# --- Model & Backend ---
# Qwen 2.5 14B (~9 GB) hiểu tiếng Việt xuất sắc và hỗ trợ function calling chuẩn xác.
# Với 2x T4 16GB (32GB VRAM), model chạy cực nhanh và ổn định.
# Tùy chọn khác: "qwen2.5:7b" (tải nhanh hơn ~4.7GB), "llama3.1:8b"
MODEL_NAME         = "qwen2.5:14b"
LLM_BACKEND        = "ollama"           # "ollama" (khuyên dùng) hoặc "external" (nếu tự chạy llama-server 8080)
EXTERNAL_LLM_URL   = "http://localhost:8080/v1"

# --- Target Server ---
TARGET_PORT        = 8000
DEFENSE_PROFILE    = "none"             # none | basic | strict

# --- Git Repo & Branch ---
REPO_URL           = "https://github.com/TranQuangMinh-2005/RedLine.git"
BRANCH             = "main"

# --- Kaggle Secrets (Add-ons -> Secrets) ---
NGROK_TOKEN_SECRET = "NGROK_AUTH_TOKEN"  # BẮT BUỘC (hoặc NGROK_AUTHTOKEN)
# =====================================================================

WORKING_DIR = "/kaggle/working"
REPO_DIR    = f"{WORKING_DIR}/RedLine" if os.path.exists(WORKING_DIR) else os.getcwd()
LOG_DIR     = "/kaggle/temp" if os.path.exists("/kaggle") else "./temp"
OLLAMA_LOG  = f"{LOG_DIR}/ollama.log"
TARGET_LOG  = f"{LOG_DIR}/target.log"

os.makedirs(LOG_DIR, exist_ok=True)


# --------------------------- helpers ---------------------------------
def sh(cmd, check=True):
    print(f"\n$ {cmd}", flush=True)
    return subprocess.run(cmd, shell=True, check=check)


def sh_args(args, check=True):
    print("\n$ " + " ".join(shlex.quote(str(a)) for a in args), flush=True)
    return subprocess.run([str(a) for a in args], check=check)


def require_internet():
    try:
        with urllib.request.urlopen("https://github.com", timeout=8) as r:
            print(f">>> Internet OK: github.com HTTP {r.status}", flush=True)
    except Exception as e:
        print("!!! Kaggle Internet đang OFF. Session options -> Internet = On, "
              f"restart rồi chạy lại. ({type(e).__name__}: {e})", flush=True)
        sys.exit(2)


def require_free_space(path, need_gib):
    free = shutil.disk_usage(path).free / 1024**3
    print(f">>> Disk free {path}: {free:.1f} GiB (cần ~{need_gib:.1f} GiB)", flush=True)
    if free < need_gib:
        print("!!! Không đủ dung lượng ổ đĩa. Vui lòng dọn dẹp hoặc chọn model nhỏ hơn.", flush=True)
        sys.exit(2)


def get_gpu_count():
    try:
        res = subprocess.run("nvidia-smi -L", shell=True, check=False,
                             capture_output=True, text=True)
        return max(1, sum(1 for line in res.stdout.splitlines() if line.strip().startswith("GPU ")))
    except Exception:
        return 1


def get_secret(name, required=False):
    # 1. Kiểm tra biến môi trường trước
    for var in (name, "NGROK_AUTH_TOKEN", "NGROK_AUTHTOKEN", "NGROK_TOKEN"):
        val = os.environ.get(var)
        if val and val.strip():
            return val.strip()

    # 2. Kiểm tra Kaggle Secrets
    try:
        from kaggle_secrets import UserSecretsClient

        user_secrets = UserSecretsClient()
        for s in (name, "NGROK_AUTH_TOKEN", "NGROK_AUTHTOKEN", "NGROK_TOKEN"):
            try:
                val = user_secrets.get_secret(s)
                if val and val.strip():
                    return val.strip()
            except Exception:
                pass
    except Exception as e:
        if required:
            print(f"!!! Thiếu Secret bắt buộc '{name}'. Add-ons -> Secrets, nhớ bật Attach. ({e})",
                  flush=True)
            sys.exit(2)
    return ""


def pull_ollama_model(model_name: str):
    """Tải model qua Ollama HTTP API với thanh tiến độ gọn gàng (không spam log Notebook)."""
    print(f">>> Đang tải '{model_name}' (mất ~2-3 phút trên kết nối Kaggle)...", flush=True)
    pull_url = "http://localhost:11434/api/pull"
    payload = json.dumps({"name": model_name, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        pull_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    last_pct = -1
    last_status = None
    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            for raw_line in resp:
                if not raw_line:
                    continue
                try:
                    chunk = json.loads(raw_line.decode("utf-8"))
                except Exception:
                    continue

                status = chunk.get("status", "")
                total = chunk.get("total", 0)
                completed = chunk.get("completed", 0)

                if total and total > 50 * 1024 * 1024:  # File weights chính (>50MB)
                    pct = int(completed / total * 100)
                    if pct != last_pct and pct % 10 == 0:
                        last_pct = pct
                        total_gib = total / (1024**3)
                        comp_gib = completed / (1024**3)
                        print(f"    - Tiến độ tải: {pct}% ({comp_gib:.1f}/{total_gib:.1f} GiB)", flush=True)
                elif status and status != last_status:
                    if not status.startswith("downloading"):
                        print(f"    - {status}", flush=True)
                        last_status = status
    except Exception as exc:
        print(f"!!! Lỗi khi stream pull qua API ({exc}), chuyển sang lệnh dự phòng...", flush=True)
        sh(f"ollama pull {model_name}")


def warmup_ollama_model(model_name: str):
    """Nạp trước model vào GPU VRAM (Warm-up) để tránh cold-start khi gửi tin nhắn đầu tiên."""
    print(">>> Nạp trước mô hình vào VRAM GPU (Warm-up)...", flush=True)
    t0 = time.time()
    try:
        url = "http://localhost:11434/api/generate"
        payload = json.dumps({
            "model": model_name,
            "prompt": "hi",
            "stream": False,
            "keep_alive": "24h",
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            _ = resp.read()
        dur = round(time.time() - t0, 1)
        print(f">>> Mô hình đã nạp sẵn vào GPU VRAM (xong sau {dur}s, sẵn sàng trả lời ngay).", flush=True)
    except Exception as exc:
        print(f">>> Bỏ qua bước warm-up: {exc}", flush=True)


# =====================================================================
#  MAIN
# =====================================================================
line = "=" * 68
print("\n" + line)
print(" 🚀 KHỞI ĐỘNG REDLINE RAG AGENT TRÊN KAGGLE (2x T4 GPU) ".center(68, "="))
print(line)

# --- 1) Kiểm tra môi trường ---
require_internet()
ngrok_token = get_secret(NGROK_TOKEN_SECRET, required=True)
gpu_count = get_gpu_count()
sh("nvidia-smi -L", check=False)
print(f">>> Phát hiện {gpu_count} GPU sẵn sàng cho mô hình.", flush=True)

# --- 2) Clone hoặc Update Repo RedLine ---
if os.path.exists(WORKING_DIR):
    os.chdir(WORKING_DIR)

if not os.path.isdir(REPO_DIR):
    print(f">>> Clone repository từ {REPO_URL} (branch: {BRANCH})...", flush=True)
    sh(f"git clone -b {BRANCH} {REPO_URL} {REPO_DIR}")
    os.chdir(REPO_DIR)
else:
    print(f">>> Cập nhật repository tại {REPO_DIR}...", flush=True)
    os.chdir(REPO_DIR)
    sh("git fetch origin", check=False)
    sh(f"git checkout {BRANCH}", check=False)
    sh(f"git pull origin {BRANCH}", check=False)

# --- 3) Cài đặt Dependencies Python ---
print(">>> Cài đặt các thư viện phụ thuộc Python...", flush=True)
sh(f"{sys.executable} -m pip install -q -e . pyngrok")

# --- 4) Cài đặt và khởi chạy LLM Backend ---
if LLM_BACKEND == "ollama":
    require_free_space("/kaggle/temp" if os.path.exists("/kaggle") else ".", 15)

    # Đảm bảo /usr/local/bin nằm trong PATH
    if "/usr/local/bin" not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"/usr/local/bin:{os.environ.get('PATH', '')}"

    # Cài Ollama nếu chưa có
    if not shutil.which("ollama"):
        print(">>> Cài đặt zstd và Ollama Linux...", flush=True)
        # zstd bắt buộc để giải nén bộ cài Ollama mới nhất
        sh("which zstd >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq zstd) || (sudo apt-get update -qq && sudo apt-get install -y -qq zstd)", check=False)
        sh("curl -fsSL https://ollama.com/install.sh | sh")

    # Khởi động Ollama daemon trong background
    ollama_ready = False
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            if r.status == 200:
                ollama_ready = True
    except Exception:
        ollama_ready = False

    if not ollama_ready:
        print(f">>> Khởi động Ollama daemon (log: {OLLAMA_LOG})...", flush=True)
        os.environ["OLLAMA_KEEP_ALIVE"] = "24h"
        ollama_env = os.environ.copy()
        ollama_env["OLLAMA_KEEP_ALIVE"] = "24h"
        ollama_log_file = open(OLLAMA_LOG, "w")
        subprocess.Popen(["ollama", "serve"], stdout=ollama_log_file, stderr=subprocess.STDOUT, env=ollama_env)

        t0 = time.time()
        while time.time() - t0 < 30:
            try:
                with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
                    if r.status == 200:
                        ollama_ready = True
                        break
            except Exception:
                time.sleep(1)

    if not ollama_ready:
        print("!!! Không thể kết nối tới Ollama. Xem log:", flush=True)
        sh(f"tail -n 50 {OLLAMA_LOG}", check=False)
        sys.exit(1)
    print(">>> Ollama daemon đã sẵn sàng.", flush=True)

    # Kiểm tra và tải model
    print(f">>> Kiểm tra mô hình '{MODEL_NAME}' trong Ollama...", flush=True)
    need_pull = True
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            installed = [m.get("name", "") for m in data.get("models", [])]
            base_name = MODEL_NAME.split(":")[0]
            if any(MODEL_NAME in n or base_name in n for n in installed):
                need_pull = False
    except Exception:
        need_pull = True

    if need_pull:
        pull_ollama_model(MODEL_NAME)
    else:
        print(f">>> Mô hình '{MODEL_NAME}' đã có sẵn trong Ollama cache.", flush=True)

    warmup_ollama_model(MODEL_NAME)
    print(f">>> Mô hình '{MODEL_NAME}' đã sẵn sàng trên 2x T4 GPU.", flush=True)

    llm_base_url = "http://localhost:11434/v1"
    llm_model = MODEL_NAME
else:
    # Kết nối tới external server (ví dụ llama-server chạy trước đó trên port 8080)
    llm_base_url = EXTERNAL_LLM_URL
    llm_model = MODEL_NAME
    print(f">>> Sử dụng external LLM server tại {llm_base_url} (model: {llm_model})", flush=True)

# --- 5) Seed Database Mock & Ingest RAG Knowledge Base ---
print("\n>>> Nạp dữ liệu sandbox...", flush=True)
# Đặt cấu hình môi trường cho RedLine
os.environ["PYTHONPATH"] = f"{REPO_DIR}:{os.environ.get('PYTHONPATH', '')}"
os.environ["LLM_PROVIDER"] = "ollama" if LLM_BACKEND == "ollama" else "external"
os.environ["LLM_MODEL"] = llm_model
os.environ["LLM_BASE_URL"] = llm_base_url
os.environ["LLM_API_KEY"] = "ollama"
os.environ["DATABASE_URL"] = "sqlite:///./data/redline.db"
os.environ["DEFENSE_PROFILE"] = DEFENSE_PROFILE

sh(f"{sys.executable} -m src.db.seed_data")
sh(f"{sys.executable} scripts/ingest_rag.py")

# --- 6) Mở ngrok tunnel ---
print("\n>>> Khởi tạo ngrok tunnel ra Internet...", flush=True)
from pyngrok import conf, ngrok

conf.get_default().auth_token = ngrok_token
ngrok.kill()
public_tunnel = ngrok.connect(TARGET_PORT, "http")
api_base = public_tunnel.public_url

# --- 7) Khởi động FastAPI Target Agent ---
print(f">>> Khởi động FastAPI Target Agent trên cổng {TARGET_PORT} (log: {TARGET_LOG})...", flush=True)
target_log_file = open(TARGET_LOG, "w")
agent_proc = subprocess.Popen(
    [
        sys.executable, "-m", "uvicorn", "src.main:app",
        "--host", "0.0.0.0",
        "--port", str(TARGET_PORT),
    ],
    stdout=target_log_file,
    stderr=subprocess.STDOUT,
    cwd=REPO_DIR,
)

# Chờ server sẵn sàng
t0 = time.time()
server_ready = False
while time.time() - t0 < 60:
    if agent_proc.poll() is not None:
        print("\n!!! FastAPI server đã thoát. Log lỗi:", flush=True)
        sh(f"tail -n 50 {TARGET_LOG}", check=False)
        sys.exit(1)
    try:
        with urllib.request.urlopen(f"http://localhost:{TARGET_PORT}/health", timeout=2) as r:
            if r.status == 200:
                server_ready = True
                break
    except Exception:
        time.sleep(1)

if not server_ready:
    print("!!! Timeout chờ FastAPI server. Log:", flush=True)
    sh(f"tail -n 50 {TARGET_LOG}", check=False)
    sys.exit(1)

# --- 8) Hiển thị thông tin kết nối và stream log ---
print("\n" + line)
print(" SẴN SÀNG — REDLINE TARGET AGENT ĐANG CHẠY ".center(68, "="))
print(line)
print(f"Public API Base : {api_base}")
print(f"Healthcheck     : {api_base}/health")
print(f"Chat Native     : {api_base}/chat")
print(f"OpenAI Base URL : {api_base}/v1")
print(f"OpenAI Models   : {api_base}/v1/models")
print(f"OpenAI Chat     : {api_base}/v1/chat/completions")
print(f"Model           : {llm_model} (chạy trên {gpu_count} GPU)")
print(f"RAG Knowledge   : 14 Markdown documents trong data/rag/documents/")
print(f"Database        : SQLite sandbox (mock customers, orders, tickets)")
print(f"Defense Profile : {DEFENSE_PROFILE}")
print(line)
print("Ví dụ 1 — Gọi qua endpoint /chat (RedLine native):")
print(f"  curl -X POST {api_base}/chat \\")
print("    -H 'Content-Type: application/json' \\")
print("    -H 'ngrok-skip-browser-warning: true' \\")
print("    -d '{\"message\":\"Chính sách đổi trả hàng như thế nào?\"}'")
print("\nVí dụ 2 — Gọi qua endpoint /v1/chat/completions (Chuẩn OpenAI):")
print(f"  curl -X POST {api_base}/v1/chat/completions \\")
print("    -H 'Content-Type: application/json' \\")
print("    -H 'ngrok-skip-browser-warning: true' \\")
print(f"    -d '{{\"model\":\"{llm_model}\", \"messages\":[{{\"role\":\"user\", \"content\":\"Kiểm tra thông tin khách hàng CUS-001\"}}]}}'")
print(line)
print("Dừng session: Bấm 'Stop session' trên Kaggle (ngừng tính quota GPU).")
print(line + "\nĐang stream log FastAPI server...\n", flush=True)

# Giữ cell sống và stream log ra màn hình
sh(f"tail -n +1 -f {TARGET_LOG}", check=False)
