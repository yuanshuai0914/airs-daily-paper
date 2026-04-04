# dailypaper-skills

我平时读论文用的一套 Claude Code skills。跟 Claude 说句话就能筛论文、读论文、写笔记，最后自动存进本地 Markdown 知识库；默认兼容 Obsidian，也可以同步到 Feishu。

> **新分支更新**
> Codex / Humanoid 的分支：[`codex+humanoid`](https://github.com/huangkiki/dailypaper-skills/tree/codex%2Bhumanoid)。
> 如果你想直接看 Codex 适配版本，建议先从这个分支开始。

> 📺 [用 Claude Code 打造我的论文流水线](http://xhslink.com/o/1dhQCn40EWY) — 我随手拍的一段视频展示效果

## 🦴 这套东西会帮我做什么

- 抓取每日新论文，初筛后生成推荐列表。
- 支持完整解析、快速摘要和批判性分析。
- 术语可沉淀为概念笔记，方便后续串联。
- 自动写入本地 Markdown 知识库，并维护目录页和导航页。
- 可选同步到 Feishu 文档，减少对 Obsidian 的依赖。
- 可接入 Zotero，省去手动复制链接。

最终生成结果在本地知识库里大概会长这样：

```text
PaperKnowledgeBase/
├── DailyPapers/YYYY-MM-DD-论文推荐.md
├── 论文笔记/.../*.md
└── 论文笔记/_概念/.../*.md
```

可直接看模板：

- [Obsidian 模板](obsidian-templates/论文笔记模板.md)

## 🐕 怎么用

基本就 2 句：

```text
今日论文推荐
读一下这篇论文 https://arxiv.org/abs/2509.24527
```

其他常见说法：

```text
过去3天论文推荐
过去一周论文推荐

读一下这篇论文 ~/Downloads/paper.pdf
快速看一下这篇论文 https://arxiv.org/abs/2509.24527
批判性分析这篇论文 ~/Downloads/paper.pdf

读一下 Zotero 里的 Diffusion Policy
批量读一下 Zotero 里 VLA 分类下的论文
```

`今日论文推荐` 会跑完整流程，`读一下这篇论文 ...` 用来读单篇。

目录页一般会自动更新；如果你手动改过结构，或者怀疑没同步，再补一句：

```text
更新索引
```

## 🏡 安装

前置环境：

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- [Python 3.8+](https://www.python.org/)
- [`poppler-utils`](https://poppler.freedesktop.org/)（`apt install poppler-utils` / `brew install poppler`）
- [Zotero](https://www.zotero.org/)（可选）
- [Feishu CLI / lark-cli](https://github.com/larksuite/cli/)（如果你想同步到飞书）

建议给本地知识库目录加上 git 版本管理。笔记多了以后有个版本历史会安心很多，也方便多设备同步。

如果你是在自己的本地机器上日常使用，通常直接用 `claude --dangerously-skip-permissions` 会省很多权限确认；前提是你清楚这会跳过权限检查，所以更适合个人环境，不建议在不熟悉的机器上直接这么跑。

在仓库根目录运行：

```bash
mkdir -p ~/.claude/skills
cp -r ./skills/* ~/.claude/skills/

# 改成你自己的本地知识库路径，要跟配置文件里的 paths.knowledge_base_root 一致
VAULT=~/PaperKnowledgeBase
mkdir -p "$VAULT/DailyPapers" \
  "$VAULT/论文笔记/_概念/0-待分类" \
  "$VAULT/论文笔记/_待整理"
```

## ⚙️ 配置

安装完之后需要改一下配置。配置文件是 `~/.claude/skills/_shared/user-config.json`，可以自己改，也可以直接告诉 Claude 你的需求让它帮你改。

里面主要改这几项：

| 配置项 | 说明 |
| --- | --- |
| `paths.knowledge_base_root` | 本地 Markdown 知识库路径 |
| `paths.obsidian_vault` | 旧字段，兼容保留；没配 `knowledge_base_root` 时会回退到这里 |
| `paths.zotero_db` | Zotero 数据库路径（不用 Zotero 可以不填） |
| `paths.zotero_storage` | Zotero 附件存储路径 |
| `daily_papers.keywords` | 你关心的研究方向，用来给论文打分 |
| `daily_papers.negative_keywords` | 你不想看的方向，命中直接排除 |
| `daily_papers.domain_boost_keywords` | 额外加分的领域词 |
| `publishing.backend` | 发布后端：`obsidian` 或 `feishu` |
| `publishing.auto_sync` | 生成/更新 Markdown 后是否自动同步到 Feishu |
| `publishing.feishu.cli_path` | `lark-cli` 可执行文件路径 |
| `publishing.feishu.wiki_space` / `folder_token` | Feishu 文档的目标空间或目录 |

`批量读一下 Zotero 里 XXX 分类下的论文` 不需要额外的映射文件；只要 `paths.zotero_db` 和 `paths.zotero_storage` 配对，脚本会直接从你的 Zotero 分类树里查。

## 🦮 默认行为

默认本地知识库管理不会自动 commit、push：

- `auto_refresh_indexes = true`
- `git_commit = false`
- `git_push = false`

也就是默认会自动刷新目录页，但不会动你的 git。如果你的本地知识库已经用 git 管理，希望跑完流程后自动提交，把 `git_commit` 打开就行。

## Feishu 同步

如果你不用 Obsidian，只想把结果发到 Feishu，可以这样配：

```json
{
  "paths": {
    "knowledge_base_root": "~/PaperKnowledgeBase"
  },
  "publishing": {
    "backend": "feishu",
    "auto_sync": true,
    "feishu": {
      "cli_path": "~/.npm-global/bin/lark-cli",
      "wiki_space": "my_library"
    }
  }
}
```

第一次使用前先装并登录 `lark-cli`：

```bash
npm install -g @larksuite/cli
lark-cli config init
lark-cli auth login --recommend
```

仓库里新增了 `skills/_shared/feishu_sync.py`。在 `backend=feishu` 且 `auto_sync=true` 时，相关 skill 会在本地 Markdown 落盘后调用这个脚本，把每日推荐、论文笔记和概念笔记同步成 Feishu 文档。

如果 `lark-cli` 不在你的 `PATH` 里，把 `publishing.feishu.cli_path` 改成它的绝对路径就行。

## 🐾 大概怎么跑的

**每日推荐**拆成三步流水线，避免单次上下文太长：

1. **抓取**：Python 脚本并发请求 HuggingFace Daily / Trending + arXiv API，按你配的关键词打分、去重，输出 top 30 候选到 `/tmp`。然后异步抓 arXiv 页面补全作者、机构、图片等元数据。
2. **点评**：Claude 读候选列表，按 必读 / 值得看 / 可跳过 分流，写锐评，保存到本地知识库的 `DailyPapers/` 目录，同时更新 `.history.json` 做跨天去重。
3. **笔记**：对"必读"论文逐篇调 paper-reader 生成完整笔记（公式、图表、关键方法），顺便补概念库，最后回填链接、刷新目录页。

**读单篇**走 paper-reader：支持 arXiv 链接、本地 PDF、Zotero 搜索。会从 arXiv HTML / 项目主页 / PDF 多路取图，按模板生成结构化笔记，自动归类到本地知识库对应目录；如果启用了 Feishu，同步后会在飞书里生成对应文档。

**目录页**由 `generate-mocs` 维护：递归扫描论文笔记和概念库目录，自动生成带 wikilink 的索引页。

更多实现细节见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 🏠 仓库里有什么

平时真正常用的是前 2 个，后 1 个偏维护：

- `daily-papers`：每日推荐全流程
- `paper-reader`：读单篇论文
- `generate-mocs`：手动补刷目录页

另外还有 3 个内部 skill，主要给调试和重跑单步用：

- `daily-papers-fetch`
- `daily-papers-review`
- `daily-papers-notes`

## 🎾 进阶用法

如果你只想单独跑流水线某一步，也可以分别说：

```text
跑一下论文抓取
跑一下论文点评
跑一下论文笔记
```

如果你想做本地定时任务（比如每天早上6点自动运行），可以直接让 Claude 按你的系统环境帮你配置。

## 🐶 FAQ

**可以一步跑完整流程吗？**

可以。直接说 `今日论文推荐` 就行。内部拆成三步主要是为了避免单次上下文过长，同时方便单步调试和重跑。

**目录页会自动刷新吗？**

默认会。读单篇论文和跑完整的每日推荐流程时，结束后通常都会自动刷新一次。`更新索引` 更像是手动补刷入口。

**不用 Zotero 可以吗？**

可以。每日推荐不依赖 Zotero，单篇阅读也支持直接输入 arXiv 链接或本地 PDF。Zotero 主要用于已有文献库的搜索、归类和批量处理。

**不用 Obsidian 可以吗？**

可以。输出本质上是 Markdown 文件，不强绑 Obsidian。现在也支持通过 `lark-cli` 同步到 Feishu；本地目录仍然会保留一份 Markdown 作为缓存和索引来源。

**可以用来辅助论文写作吗？**

可以，比较适合用来整理 related work、维护笔记库和生成阅读提纲。AI 生成的内容建议自己核验后再使用。

**默认会动我的 git 仓库吗？**

不会。`commit / push` 默认关闭，只有你自己打开配置后才会执行。

## ⚠️ 免责声明

这是我个人研究工作流的开源整理。AI 生成的推荐、点评和笔记可能有事实错误或遗漏，所以更适合作为辅助工具，而不是直接替代你的研究判断。

另外，这套东西难免会有 bug，平台和环境适配问题也很正常；如果你遇到小问题，最省事的办法通常就是直接让 AI 帮你一起改。

## ⭐ 支持这个项目

如果这套 workflow 对你有帮助，欢迎提 PR、开 issue，或者顺手点个 Star。像 [`codex+humanoid`](https://github.com/huangkiki/dailypaper-skills/tree/codex%2Bhumanoid) 这种兼容性适配也很欢迎，一起补会比我一个人慢慢填坑快很多。

[![Star History Chart](https://api.star-history.com/svg?repos=huangkiki/dailypaper-skills&type=Date)](https://www.star-history.com/#huangkiki/dailypaper-skills&Date)

## License

Apache-2.0. See `LICENSE`.
