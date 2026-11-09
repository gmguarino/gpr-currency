#!/usr/bin/env bash
# Serve a model with vLLM (OpenAI-compatible API) on a GPU machine, using Docker.
#
# Usage:   deploy/serve_vllm.sh [start|stop|restart|status|logs|test]
#   start    run the vLLM container and wait until the server is ready (default)
#   stop     stop and remove the container
#   restart  stop, then start
#   status   show container state and GPU memory
#   logs     follow the container logs
#   test     send one sample sentiment request to the running server
#
# Configure with environment variables (defaults in brackets):
#   MODEL                    Hugging Face model id            [Qwen/Qwen3.5-9B]
#   SERVED_MODEL_NAME        name clients use in requests     [qwen]
#   PORT                     port on the host                 [8000]
#   BIND                     host address to bind             [127.0.0.1]  (0.0.0.0 exposes it; set VLLM_API_KEY then)
#   MAX_MODEL_LEN            max context tokens               [4096]
#   GPU_MEMORY_UTILIZATION   fraction of GPU memory for vLLM  [0.90]
#   MAX_NUM_SEQS             max requests batched together    [128]
#   DTYPE                    auto | bfloat16 | float16        [auto]
#   QUANTIZATION             e.g. fp8 (halves weight memory; use on a 24 GB L4)  [none]
#   EXTRA_ARGS               extra arguments passed to vLLM   [none]
#   VLLM_IMAGE               Docker image                     [vllm/vllm-openai:latest]
#   VLLM_API_KEY             require this key from clients    [none]
#   HF_TOKEN                 Hugging Face token (only for gated models)
#   HF_CACHE                 model cache dir on the host      [~/.cache/huggingface]
#   CONTAINER_NAME           Docker container name            [vllm]
#   WAIT_MINUTES             how long `start` waits for the server  [30]
#   DRY_RUN=1                print the docker command and exit
#
# Examples:
#   deploy/serve_vllm.sh                                   # 9B on an L40S / H100
#   QUANTIZATION=fp8 deploy/serve_vllm.sh                  # 9B on a 24 GB L4
#   MODEL=Qwen/Qwen3.5-4B deploy/serve_vllm.sh restart     # smaller model
#
# The server listens on localhost only by default. Run the scoring client on the same
# machine, or reach it from your laptop through an SSH tunnel:
#   ssh -L 8000:localhost:8000 ubuntu@<instance-ip>

set -euo pipefail

MODEL="${MODEL:-Qwen/Qwen3.5-9B}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-qwen}"
PORT="${PORT:-8000}"
BIND="${BIND:-127.0.0.1}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.90}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-128}"
DTYPE="${DTYPE:-auto}"
QUANTIZATION="${QUANTIZATION:-}"
EXTRA_ARGS="${EXTRA_ARGS:-}"
VLLM_IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:latest}"
VLLM_API_KEY="${VLLM_API_KEY:-}"
HF_CACHE="${HF_CACHE:-$HOME/.cache/huggingface}"
CONTAINER_NAME="${CONTAINER_NAME:-vllm}"
WAIT_MINUTES="${WAIT_MINUTES:-30}"

die() { echo "error: $*" >&2; exit 1; }

check_prereqs() {
  command -v docker >/dev/null || die "docker not found. Use a Scaleway 'GPU OS' image (NVIDIA drivers + Docker + NVIDIA container toolkit)."
  command -v nvidia-smi >/dev/null || die "nvidia-smi not found: NVIDIA drivers are missing."
  nvidia-smi -L >/dev/null 2>&1 || die "no GPU visible (nvidia-smi -L failed)."
}

build_args() {
  ARGS=(--model "$MODEL" --served-model-name "$SERVED_MODEL_NAME"
        --max-model-len "$MAX_MODEL_LEN" --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
        --max-num-seqs "$MAX_NUM_SEQS" --dtype "$DTYPE")
  [[ -n "$QUANTIZATION" ]] && ARGS+=(--quantization "$QUANTIZATION")
  [[ -n "$VLLM_API_KEY" ]] && ARGS+=(--api-key "$VLLM_API_KEY")
  # shellcheck disable=SC2206  # intentional word splitting of user-provided extra args
  [[ -n "$EXTRA_ARGS" ]] && ARGS+=($EXTRA_ARGS)
  return 0
}

docker_cmd() {
  DOCKER=(docker run -d --name "$CONTAINER_NAME" --gpus all --ipc=host --restart unless-stopped
          -p "$BIND:$PORT:8000" -v "$HF_CACHE:/root/.cache/huggingface")
  [[ -n "${HF_TOKEN:-}" ]] && DOCKER+=(-e "HF_TOKEN=$HF_TOKEN")
  DOCKER+=("$VLLM_IMAGE" "${ARGS[@]}")
}

auth_header() { [[ -n "$VLLM_API_KEY" ]] && echo "Authorization: Bearer $VLLM_API_KEY" || echo "X-Unused: 1"; }

cmd_stop() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 && echo "stopped $CONTAINER_NAME" || echo "$CONTAINER_NAME not running"
}

cmd_start() {
  build_args; docker_cmd
  if [[ "${DRY_RUN:-0}" == "1" ]]; then printf '%q ' "${DOCKER[@]}"; echo; return; fi
  check_prereqs
  mkdir -p "$HF_CACHE"
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  echo "Pulling $VLLM_IMAGE (first time only) ..."
  docker pull "$VLLM_IMAGE" >/dev/null
  echo "Starting $MODEL on port $PORT (the first start downloads the weights, ~18 GB for 9B) ..."
  "${DOCKER[@]}" >/dev/null
  local deadline=$((SECONDS + WAIT_MINUTES * 60))
  until curl -sf -H "$(auth_header)" "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; do
    docker ps --filter "name=^${CONTAINER_NAME}$" --filter status=running -q | grep -q . \
      || { docker logs --tail 40 "$CONTAINER_NAME" >&2; die "container exited, see the log above"; }
    (( SECONDS < deadline )) || { docker logs --tail 40 "$CONTAINER_NAME" >&2; die "not ready after ${WAIT_MINUTES} min"; }
    echo "  waiting for the server ... ($(docker logs --tail 1 "$CONTAINER_NAME" 2>&1 | cut -c1-110))"
    sleep 15
  done
  echo "Ready: http://127.0.0.1:$PORT/v1  (model name: $SERVED_MODEL_NAME)"
  echo "Try:   $0 test"
}

cmd_test() {
  local body
  body=$(cat <<JSON
{"model": "$SERVED_MODEL_NAME", "temperature": 0, "max_tokens": 80,
 "chat_template_kwargs": {"enable_thinking": false},
 "messages": [{"role": "user", "content":
   "Rate from 1 (completely negative) to 5 (completely positive) the attitude towards the United States in this sentence, and answer in JSON with score and reason: 美方一再无理打压中国企业，中方对此坚决反对。"}]}
JSON
)
  curl -sf -H "Content-Type: application/json" -H "$(auth_header)" \
    "http://127.0.0.1:$PORT/v1/chat/completions" -d "$body" \
    | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r["choices"][0]["message"]["content"]); print("usage:", r["usage"])' \
    || die "request failed; is the server up? ($0 status / $0 logs)"
}

case "${1:-start}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status)  docker ps -a --filter "name=^${CONTAINER_NAME}$"; nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv ;;
  logs)    docker logs -f "$CONTAINER_NAME" ;;
  test)    cmd_test ;;
  -h|--help|help) sed -n '2,38p' "$0" ;;
  *) die "unknown command '$1' (use start|stop|restart|status|logs|test)" ;;
esac
