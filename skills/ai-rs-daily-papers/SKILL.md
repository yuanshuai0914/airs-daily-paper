# AI RS Daily Papers

Daily paper recommendations for Remote Sensing and World Model research.

## Overview

This skill fetches recent papers from **arXiv + HuggingFace Daily/Trending + OpenReview (best-effort)**, then filters/ranks them by:
- **Remote Sensing**: satellite imagery, earth observation, hyperspectral, SAR
- **World Model**: video generation, diffusion models, generative AI
- **Multimodal**: VLM/MLLM, vision-language
- **Agent**: agentic AI, tool use, planning

> OpenReview 可能在部分网络环境返回 403。当前实现会自动探测可用 API；若不可用会自动降级为 arXiv + HuggingFace，不会中断整条流程。

**⏰ 定时执行**: 默认不会自动运行！需要手动安装 LaunchAgent（见下方 macOS Automation 部分）

## Files

| File | Description |
|------|-------------|
| `generator.py` | Core logic to fetch and filter papers |
| `script.sh` | Shell wrapper for manual execution |
| `run_and_send.sh` | Generate report and send to Feishu |
| `com.ai-rs-daily-papers.plist` | macOS LaunchAgent template for automation |
| `recommendations/` | Generated markdown reports (YYYY-MM-DD.md) |

## Usage

### Manual Generation

```bash
cd ~/.openclaw/workspace/skills/ai-rs-daily-papers

# Generate full report (default: HF daily only today)
./script.sh

# Generate compact summary (for Feishu)
./script.sh --compact

# Fetch HF daily with N-day window (also includes HF trending)
./script.sh --compact --days=3

# Custom output path
./script.sh /path/to/output.md
```

### Send to Feishu

```bash
export FEISHU_TARGET="your_chat_id"
export AI_RS_DAILY_PAPERS_PROXY="http://proxy:port"  # optional

# default days=1
./run_and_send.sh

# specify HF daily fetch window
./run_and_send.sh --days 3
# or: ./run_and_send.sh --days=7
```

## macOS Automation (LaunchAgent)

1. Create logs directory:
   ```bash
   mkdir -p ~/.openclaw/workspace/skills/ai-rs-daily-papers/logs
   ```

2. Edit the plist file and set `YOUR_FEISHU_TARGET_HERE` to your actual Feishu chat ID

3. Install the LaunchAgent:
   ```bash
   cp com.ai-rs-daily-papers.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.ai-rs-daily-papers.plist
   ```

4. Verify it's loaded:
   ```bash
   launchctl list | grep ai-rs-daily-papers
   ```

5. To run immediately (for testing):
   ```bash
   launchctl start com.ai-rs-daily-papers
   ```

6. To unload:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.ai-rs-daily-papers.plist
   ```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FEISHU_TARGET` | Yes* | Feishu chat ID or user ID to send messages |
| `AI_RS_DAILY_PAPERS_PROXY` | No | HTTP/HTTPS proxy for API requests |

*Required for `run_and_send.sh` only

## Output Format

### Markdown Report

Full reports are saved to `recommendations/YYYY-MM-DD.md` with:
- Paper title
- Source (arxiv/openreview)
- Upvotes (where available)
- Abstract/summary
- Direct link

### Compact Summary

For Feishu messages, a condensed format:
```
📚 AI Daily Papers - 2025-01-15

🛰️ Remote Sensing:
1. Paper Title Here (arxiv)
2. Another Paper (openreview)
...

🌍 World Model:
1. Video Generation Paper (arxiv)
...
```

## Data Sources

- **arXiv**: CS.CV / CS.AI / CS.CL related queries with keyword filtering
- **HuggingFace**:
  - daily_papers (supports `--days` window)
  - trending (single global list, merged each run)
- **OpenReview** (best-effort): ICLR, NeurIPS, CVPR, ICML, ECCV, AAAI invitations (multiple years)

## OpenReview Fallback Behavior

- 系统会先自动探测 OpenReview 可用 API 基址
- 若 OpenReview 返回 403/不可达：
  - 自动降级为 **arXiv + HuggingFace**
  - 任务继续执行，不报整体失败
  - 发送消息中不会强行展示空的 OpenReview 区块

## Automation Status

**⚠️ 目前不会自动执行！**

需要手动安装 LaunchAgent 后才会每天早上8点自动运行。

## Notes

- Maximum 15 papers per category in full reports
- Maximum 5 papers per category in compact summaries
- Papers are filtered by keyword matching on title and abstract, then ranked
- `--days` controls HuggingFace daily window; trending is always merged
- No API keys required for arXiv / HuggingFace / OpenReview public endpoints
