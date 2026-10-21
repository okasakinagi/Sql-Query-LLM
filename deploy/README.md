# 大模型服务部署指南

本系统**不包含任何模型权重**，只通过 OpenAI 兼容接口调用外部模型服务。
你可以用 llama.cpp、Ollama、LM Studio、vLLM 中的任意一个，甚至接远程 API。

```
本系统  ──HTTP──▶  http://<host>:<port>/v1  ──▶  任意 OpenAI 兼容模型服务
```

只需要两行配置（写在 `.env` 里，或用环境变量）：

```ini
LLM_BASE_URL=http://127.0.0.1:8080/v1
LLM_MODEL=qwen2.5-coder-7b-instruct
```

---

## 一、先选一个方案

| 方案 | 适合场景 | 优点 | 缺点 |
|---|---|---|---|
| **llama.cpp**（本项目实测） | Windows + NVIDIA 显卡，追求延迟 | 延迟最低、显存可控、支持前缀缓存 | 需要手动下载二进制 |
| **Ollama** | 想最快跑起来 | 一条命令装完，自动管理模型 | 默认参数不针对低延迟调优 |
| **LM Studio** | 不熟悉命令行 / macOS | 图形界面，模型市场一键下载 | 资源占用略高 |
| **vLLM** | Linux 服务器、多并发 | 吞吐量最高、支持批量 | 需要 Python 环境与编译依赖 |

> 本项目在 **RTX 4060 Laptop 8GB** 上实测：7B `Q4_K_M` 解码约 **35 tokens/s**，
> 单次问答端到端 1.5~2.5 秒。这是"3 秒响应"指标的硬件基础。

---

## 二、方案 A：llama.cpp（推荐，本文以 Windows + CUDA 为准）

### 1. 下载推理引擎

到 [llama.cpp Releases](https://github.com/ggml-org/llama.cpp/releases) 查找最新的
`llama-b<版本号>-bin-win-cuda-<CUDA版本>-x64.zip`。下面是本项目验证过的版本（b10875 / CUDA 13.3）：

```powershell
# 引擎 + CUDA 运行时（两个包都要）
curl.exe -L -o llama.zip   https://github.com/ggml-org/llama.cpp/releases/download/b10875/llama-b10875-bin-win-cuda-13.3-x64.zip
curl.exe -L -o cudart.zip  https://github.com/ggml-org/llama.cpp/releases/download/b10875/cudart-llama-bin-win-cuda-13.3-x64.zip
```

解压到 `deploy/runtime/`，最终应形成：

```
deploy/runtime/llama.cpp/
├─ llama-server.exe
├─ ggml-cuda.dll
├─ cublas64_13.dll
├─ cublasLt64_13.dll
├─ cudart64_13.dll
└─ ...（其余 dll）
```

> **注意**：`cudart` 包里的 DLL 必须和 `llama-server.exe` **放在同一目录**，
> 否则启动时会报 `找不到 cudart64_*.dll`。

### 2. 下载模型（GGUF）

本项目使用 `Qwen2.5-Coder-7B-Instruct` 的 `Q4_K_M` 量化版本（约 4.36 GB）。
它是代码/SQL 方向微调的模型，同参数量下 SQL 生成质量明显优于通用模型。

**国内推荐（ModelScope，实测可直连）：**

```powershell
curl.exe -L -o deploy\models\qwen2.5-coder-7b-instruct-q4_k_m.gguf `
  "https://modelscope.cn/models/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/master/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
```

**海外备选（HuggingFace）：**

```powershell
curl.exe -L -o deploy\models\qwen2.5-coder-7b-instruct-q4_k_m.gguf `
  "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
```

> 模型文件 `deploy/models/` 与 `deploy/runtime/` 已在 `.gitignore` 中排除，不会被提交。

### 3. 启动

```powershell
# 后台启动 + 自动等待健康检查通过（默认端口 8080）
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\start_llama_server.ps1

# 停止
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\stop_llama_server.ps1
```

参数可覆盖：

```powershell
.\deploy\scripts\start_llama_server.ps1 `
    -ModelPath "D:\models\qwen2.5-coder-7b-instruct-q4_k_m.gguf" `
    -Port 8080 -GpuLayers 999 -Ctx 8192
```

前台运行（方便看日志）：

```powershell
.\deploy\runtime\llama.cpp\llama-server.exe `
    -m .\deploy\models\qwen2.5-coder-7b-instruct-q4_k_m.gguf `
    -ngl 999 -c 8192 --host 127.0.0.1 --port 8080 `
    --alias qwen2.5-coder-7b-instruct
```

### 4. 自检

```powershell
python -X utf8 .\deploy\scripts\check_llm.py
```

预期输出：`/v1/models` 返回 200、单次对话耗时与 tokens/s、三条 Text-to-SQL 粗测均能产出 SELECT。

---

## 三、方案 B：Ollama（最省事）

```powershell
winget install --id Ollama.Ollama -e
ollama pull qwen2.5-coder:7b
ollama serve          # 默认监听 127.0.0.1:11434
```

然后把 `.env` 改成：

```ini
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5-coder:7b
```

自检：

```powershell
python -X utf8 .\deploy\scripts\check_llm.py --base-url http://127.0.0.1:11434/v1 --model qwen2.5-coder:7b
```

---

## 四、方案 C：LM Studio

1. 安装 [LM Studio](https://lmstudio.ai/)，在「Discover」里搜索 `Qwen2.5-Coder-7B-Instruct-GGUF` 并下载 Q4_K_M。
2. 切到「Developer」页，加载模型，点击 **Start Server**（默认端口 1234）。
3. 配置：

```ini
LLM_BASE_URL=http://127.0.0.1:1234/v1
LLM_MODEL=qwen2.5-coder-7b-instruct
```

> LM Studio 对模型名的匹配比较宽松，若报 `model not found`，
> 用 `GET /v1/models` 返回的 `id` 原样填入 `LLM_MODEL`。

---

## 五、方案 D：vLLM（Linux / 服务器）

```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-Coder-7B-Instruct \
    --host 0.0.0.0 --port 8000
```

```ini
LLM_BASE_URL=http://<server-ip>:8000/v1
LLM_MODEL=Qwen/Qwen2.5-Coder-7B-Instruct
```

---

## 六、模型怎么选

本项目对模型的要求只有两条：**能稳定输出合法 SQL**、**够快**。
在原 Prompt 结构（结构文档 + 业务口径 + 3 条示例，约 1.5k tokens 输入、100~300 tokens 输出）下：

| 模型规模 | 量化 | 权重大小 | 8 GB 显存 | 预期速度 | 建议 |
|---|---|---|---|---|---|
| 7B | Q4_K_M | ≈ 4.4 GB | ✅ 约 4.9 GB 占用 | ≈ 35 tok/s（4060 Laptop） | **推荐默认** |
| 7B | Q8_0 | ≈ 8.1 GB | ❌ 临界溢出 | — | 不推荐 |
| 14B | Q4_K_M | ≈ 8.9 GB | ❌ 会溢出到内存 | 掉一个数量级 | 需要 12 GB+ 显存 |
| 32B | Q4_K_M | ≈ 19 GB | ❌ | — | 需要 24 GB 显存 |

> 经验值：**总显存需求 ≈ 权重体积 + 1~1.5 GB**（KV 缓存按 8192 上下文估算）。
> 显存不够时，llama.cpp 会把部分层卸载到内存，速度直接掉一个数量级——
> 宁可换更小的模型，也不要让它溢出。

**其它可选模型**（都支持 GGUF，只要输出格式稳定即可直接替换）：

- `Qwen2.5-Coder-1.5B-Instruct` —— 显存 <6 GB，速度快但复杂 JOIN 容易出错
- `Qwen2.5-Coder-14B-Instruct` —— 准确率更高，需要 12 GB+ 显存
- `DeepSeek-Coder-V2-Lite-Instruct` —— MoE 结构，激活参数少，速度快
- `SQLCoder-7B-2` —— 专门针对 Text-to-SQL 微调

---

## 七、接入本系统的其它方式

除了本地部署，也可以直接指向云端 OpenAI 兼容服务（注意数据合规）：

```ini
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-xxxxxxxx
```

`LLM_API_KEY` 会以 `Authorization: Bearer <key>` 的形式随请求发送；
使用本地服务时保持默认值 `not-needed` 即可。

---

## 八、常见问题

**Q：启动报 `找不到 cudart64_13.dll` / `cublas64_13.dll`**
CUDA 运行时包没解压到 `llama-server.exe` 同目录，或版本不匹配（CUDA 12 的 DLL 不能配 CUDA 13 的引擎）。

**Q：显存不足 / 速度突然变得极慢**
`-ngl 999` 会把所有层放进显存；显存不够时会自动回落到内存计算。
降低 `-Ctx`（如 4096）或换更小的量化（`Q3_K_M`）可以缓解，
最根本的办法是换更小的模型。

**Q：端口被占用**
`start_llama_server.ps1` 会提示占用进程；先执行 `stop_llama_server.ps1 -Port 8080`，
或用 `-Port 8081` 换端口，同时更新 `LLM_BASE_URL`。

**Q：`/v1/models` 通了但 `/api/ask` 报超时**
首次加载模型后第一次推理包含 CUDA 上下文初始化，可能慢 2~5 秒；
本系统在服务启动时会后台预热一次提示词缓存，请等待页面上的「模型在线」标识出现。

**Q：可以同时跑多个模型吗？**
8 GB 显存的机器不建议。多模型场景请用 vLLM 或换更大显存的机器。
