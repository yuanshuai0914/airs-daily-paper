# AI Premium Remote Sensing Papers

Fetch remote sensing papers from premium publishers: Nature, Science, and PNAS.

## Overview

This skill automatically fetches academic papers related to remote sensing, satellite monitoring, and earth observation from three prestigious publishers:

- **Nature** - Leading scientific journal
- **Science** - Premier AAAS journal  
- **PNAS** - Proceedings of the National Academy of Sciences

## API Key Requirements

| Source | API Key Required | Notes |
|--------|------------------|-------|
| Nature | Optional | RSS feed works without API key; API provides more results |
| Science | Optional | RSS feed available, may have rate limits |
| PNAS | No | Public RSS feeds available |

### API keys are optional - will use available sources only.

## Setup Instructions

### 1. Basic Setup (No API Keys)

The skill works out-of-the-box using RSS feeds:

```bash
cd ~/.openclaw/workspace/skills/ai-premium-rs-papers
./script.sh
```

### 2. With API Keys (Enhanced Results)

#### Obtaining Nature API Key

1. Visit [SpringerNature API Portal](https://dev.springernature.com/)
2. Sign up for a free API key
3. Copy your API key

#### Obtaining Science API Key

1. Visit [AAAS Developer Portal](https://www.science.org/about/
2. Contact AAAS for API access if available
3. Note: RSS feed is often sufficient

#### Set Environment Variables

```bash
export NATURE_API_KEY="your_nature_api_key"
export SCIENCE_API_KEY="your_science_api_key"
export FEISHU_TARGET="your_feishu_user_id"
```

### 3. Automated Daily Delivery

#### Install LaunchAgent (macOS)

1. Create logs directory:
```bash
mkdir -p ~/.openclaw/workspace/skills/ai-premium-rs-papers/logs
```

2. Copy and configure the plist:
```bash
# Edit the plist file first to set your API keys and FEISHU_TARGET
vim ~/.openclaw/workspace/skills/ai-premium-rs-papers/com.ai-premium-rs-papers.plist

# Copy to LaunchAgents
cp ~/.openclaw/workspace/skills/ai-premium-rs-papers/com.ai-premium-rs-papers.plist \
   ~/Library/LaunchAgents/

# Load the agent
launchctl load ~/Library/LaunchAgents/com.ai-premium-rs-papers.plist

# Start immediately (optional)
launchctl start com.ai-premium-rs-papers
```

#### Schedule

- **Runs daily at 08:30** (30 minutes after arXiv skill)
- Generates report + sends top 5 papers to Feishu

### 4. Manual Run with Feishu Send

```bash
export FEISHU_TARGET="your_feishu_user_id"
./run_and_send.sh
```

## File Structure

```
skills/ai-premium-rs-papers/
├── generator.py              # Core fetching logic
├── script.sh                 # Manual execution
├── run_and_send.sh           # Generate + send to Feishu
├── com.ai-premium-rs-papers.plist  # LaunchAgent config
├── SKILL.md                  # This file
└── recommendations/          # Generated reports
    └── YYYY-MM-DD.md
```

## Output Format

### Full Report (Markdown)

Generated at `recommendations/YYYY-MM-DD.md`:

```markdown
# Premium Remote Sensing Papers - 2024-01-15

## Summary
Total papers found: 12

| Source | Count |
|--------|-------|
| Nature | 5 |
| PNAS | 7 |

### [Paper Title](url)
- **Source:** Nature
- **Authors:** Smith et al.
- **Published:** 2024-01-15
- **DOI:** 10.1038/...
- **Abstract:** ...
```

### Feishu Summary (Compact)

```
📡 每日遥感顶刊速递 (2024-01-15)

1. **Paper Title** (Nature)
   👤 Smith, Jones et al. | 📅 2024-01-15

2. **Another Title** (PNAS)
   👤 Wang et al. | 📅 2024-01-14

... 还有 7 篇论文 (详见完整报告)
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NATURE_API_KEY` | No | SpringerNature API key for enhanced results |
| `SCIENCE_API_KEY` | No | AAAS API key (if available) |
| `PNAS_API_KEY` | No | Not typically needed |
| `FEISHU_TARGET` | For sending | Feishu user/chat ID |
| `AI_PREMIUM_RS_PAPERS_PROXY` | No | HTTP proxy URL |

### Filter Keywords

Papers are filtered for relevance to:
- `remote sensing`
- `satellite monitoring`
- `earth observation`

## Troubleshooting

### No papers found

- Check network connectivity
- Verify RSS feeds are accessible
- Some days may have no matching papers

### API errors

- RSS fallback is used automatically
- API keys may need renewal
- Check rate limits

### Feishu send fails

- Verify `FEISHU_TARGET` is set correctly
- Ensure openclaw CLI is configured
- Check Feishu permissions

## Dependencies

- Python 3.6+
- requests library (auto-installed)
- openclaw CLI (for Feishu sending)

## License

MIT - Open source, use freely.

## Updates

To update the skill, modify the files in place. The LaunchAgent will use the updated version on next run.
