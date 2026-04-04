#!/usr/bin/env python3
"""
AI RS Daily Papers - Full Workflow
- Fetch from ArXiv + OpenReview
- Keep sources separated
- Classify into 4 categories: RS / WM / MM / Agent
- Only push newly discovered papers vs last run (persistent dedup state)
- Download PDFs for newly discovered papers
"""

import os
import sys
import json
import argparse
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

# Import from generator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generator import (
    fetch_arxiv_papers,
    ARXIV_RS_QUERY,
    ARXIV_WM_QUERY,
    ARXIV_MULTIMODAL_QUERY,
    ARXIV_AGENT_QUERY,
    fetch_openreview_all,
    fetch_hf_papers,
    classify_paper,
)

PROXY = os.environ.get('AI_RS_DAILY_PAPERS_PROXY')
LLM_API_KEY = os.environ.get('AI_RS_DAILY_PAPERS_LLM_API_KEY') or os.environ.get('DEEPSEEK_API_KEY')
LLM_API_BASE = os.environ.get('AI_RS_DAILY_PAPERS_LLM_BASE') or os.environ.get('DEEPSEEK_API_BASE') or 'https://api.deepseek.com/v1'
LLM_MODEL = os.environ.get('AI_RS_DAILY_PAPERS_LLM_MODEL', 'deepseek-chat')

CATEGORIES = [
    ('rs', '🛰️ Remote Sensing'),
    ('wm', '🌍 World Model'),
    ('mm', '🧩 Multimodal'),
    ('agent', '🤖 Agent'),
]


def get_opener():
    if PROXY:
        proxy_handler = urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})
        return urllib.request.build_opener(proxy_handler)
    return urllib.request.build_opener()


def download_file(url: str, output_path: str, timeout: int = 120) -> bool:
    try:
        opener = get_opener()
        req = urllib.request.Request(url, headers={'User-Agent': 'AI-RSDailyPapers/1.0'})
        with opener.open(req, timeout=timeout) as resp:
            with open(output_path, 'wb') as f:
                f.write(resp.read())
        return True
    except Exception as e:
        print(f"Error downloading {url}: {e}", file=sys.stderr)
        return False


def sanitize_filename(title: str, max_length: int = 60) -> str:
    invalid_chars = '<>:"/\\|?*'
    filename = title
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    if len(filename) > max_length:
        filename = filename[:max_length]
    return filename.strip()


def paper_key(p: Dict) -> str:
    return f"{p.get('source', 'unknown')}::{p.get('id', '')}"


def load_state(state_file: Path) -> Dict:
    if not state_file.exists():
        return {'updated_at': None, 'sent_ids': [], 'sent_map': {}}
    try:
        data = json.loads(state_file.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return {'updated_at': None, 'sent_ids': [], 'sent_map': {}}
        data.setdefault('updated_at', None)
        data.setdefault('sent_ids', [])
        data.setdefault('sent_map', {})
        if not isinstance(data['sent_ids'], list):
            data['sent_ids'] = []
        if not isinstance(data['sent_map'], dict):
            data['sent_map'] = {}
        return data
    except Exception:
        return {'updated_at': None, 'sent_ids': [], 'sent_map': {}}


def save_state(state_file: Path, state: Dict):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state['updated_at'] = datetime.now().isoformat()
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def prune_sent_map(sent_map: Dict[str, str], dedup_days: int | None) -> Dict[str, str]:
    if dedup_days is None:
        return sent_map
    cutoff = datetime.now() - timedelta(days=dedup_days)
    out = {}
    for k, ts in sent_map.items():
        try:
            dt = datetime.fromisoformat(ts)
            if dt >= cutoff:
                out[k] = ts
        except Exception:
            continue
    return out


def init_bucket() -> Dict[str, List[Dict]]:
    return {k: [] for k, _ in CATEGORIES}


def classify_source_papers(papers: List[Dict], max_per_category: int) -> Dict[str, List[Dict]]:
    bucket = init_bucket()
    seen = set()

    for p in papers:
        key = paper_key(p)
        if key in seen:
            continue
        seen.add(key)

        cat = classify_paper(p.get('title', ''), p.get('summary', ''))
        if cat not in bucket:
            continue
        if len(bucket[cat]) >= max_per_category:
            continue
        bucket[cat].append(p)

    return bucket


def fetch_all_sources(max_per_category: int, hf_days: int = 1) -> Dict[str, Dict[str, List[Dict]]]:
    print('Fetching papers from arxiv...')
    arxiv_raw = (
        fetch_arxiv_papers(ARXIV_RS_QUERY)
        + fetch_arxiv_papers(ARXIV_WM_QUERY)
        + fetch_arxiv_papers(ARXIV_MULTIMODAL_QUERY)
        + fetch_arxiv_papers(ARXIV_AGENT_QUERY)
    )

    print('Fetching papers from openreview...')
    openreview_raw = fetch_openreview_all()

    print(f'Fetching papers from huggingface (days={hf_days})...')
    hf_raw = fetch_hf_papers(days=hf_days)

    return {
        'arxiv': classify_source_papers(arxiv_raw, max_per_category),
        'openreview': classify_source_papers(openreview_raw, max_per_category),
        'huggingface': classify_source_papers(hf_raw, max_per_category),
    }


def filter_new_only(by_source: Dict[str, Dict[str, List[Dict]]], sent_ids: set) -> Tuple[Dict[str, Dict[str, List[Dict]]], set]:
    new_by_source: Dict[str, Dict[str, List[Dict]]] = {}
    run_ids = set()

    for source, cat_map in by_source.items():
        new_by_source[source] = {}
        for cat, papers in cat_map.items():
            new_list = []
            for p in papers:
                k = paper_key(p)
                run_ids.add(k)
                if k not in sent_ids:
                    new_list.append(p)
            new_by_source[source][cat] = new_list

    return new_by_source, run_ids


def download_new_pdfs(new_by_source: Dict[str, Dict[str, List[Dict]]], pdf_root: Path) -> int:
    downloaded = 0
    pdf_root.mkdir(parents=True, exist_ok=True)

    for source, cat_map in new_by_source.items():
        source_dir = pdf_root / source
        source_dir.mkdir(parents=True, exist_ok=True)

        for cat, papers in cat_map.items():
            cat_dir = source_dir / cat
            cat_dir.mkdir(parents=True, exist_ok=True)

            for p in papers:
                pdf_url = p.get('pdf_url')
                if not pdf_url:
                    continue

                safe_title = sanitize_filename(p.get('title', 'untitled'))
                pid = p.get('id', 'unknown').replace('/', '_').replace(':', '_')
                filename = f'{pid}_{safe_title}.pdf'
                filepath = cat_dir / filename

                if filepath.exists():
                    p['local_pdf'] = str(filepath)
                    downloaded += 1
                    continue

                if download_file(pdf_url, str(filepath)):
                    p['local_pdf'] = str(filepath)
                    downloaded += 1

    return downloaded


def format_source_block(source_name: str, cat_map: Dict[str, List[Dict]], limit_each: int = 8) -> List[str]:
    lines = [f'## {source_name}']

    total = sum(len(v) for v in cat_map.values())
    if total == 0:
        lines.append('（本次无新增）')
        lines.append('')
        return lines

    for cat, title in CATEGORIES:
        lines.append(f'{title}:')
        papers = cat_map.get(cat, [])
        if not papers:
            lines.append('- 无新增')
            lines.append('')
            continue

        for i, p in enumerate(papers[:limit_each], 1):
            short_title = p['title'][:72] + '...' if len(p['title']) > 72 else p['title']
            local_file = Path(p.get('local_pdf', '')).name if p.get('local_pdf') else '未下载'
            lines.append(f'{i}. {short_title}')
            lines.append(f'   📄 {local_file}')
            lines.append(f"   🔗 {p.get('url', '')}")
            if p.get('pdf_url'):
                lines.append(f"   📎 {p.get('pdf_url')}")
        lines.append('')

    return lines


def generate_llm_summary(title: str, abstract: str, category: str, timeout: int = 45) -> Optional[str]:
    if not LLM_API_KEY or not abstract.strip():
        return None

    prompt = (
        "你是科研论文助手。请基于给定论文标题和摘要，输出2-3句中文总结，"
        "要求具体、可读，不要套话，不要编造摘要里没有的信息。"
        "最后补一句‘建议关注点：...’。"
    )
    payload = {
        'model': LLM_MODEL,
        'temperature': 0.2,
        'messages': [
            {'role': 'system', 'content': prompt},
            {
                'role': 'user',
                'content': json.dumps(
                    {'title': title, 'abstract': abstract, 'category': category},
                    ensure_ascii=False,
                ),
            },
        ],
    }

    req = urllib.request.Request(
        f"{LLM_API_BASE.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {LLM_API_KEY}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        opener = get_opener()
        with opener.open(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='ignore'))
        content = (
            data.get('choices', [{}])[0]
            .get('message', {})
            .get('content', '')
            .strip()
        )
        return content or None
    except Exception as e:
        print(f"LLM summary failed for '{title[:50]}...': {e}", file=sys.stderr)
        return None


def fallback_summary(title: str, abstract: str, category: str) -> str:
    short_abs = ' '.join((abstract or '').split())[:180]
    return (
        f"基于标题与摘要判断，这篇属于 {category.upper()} 方向，核心问题围绕《{title}》展开。"
        f"摘要显示其主要关注点是：{short_abs}。"
        "建议关注点：先看方法创新是否带来稳定的实验增益。"
    )


def export_app_feed(new_by_source: Dict[str, Dict[str, List[Dict]]], out_json: Path, out_js: Path, use_llm_summary: bool = True):
    cards = []
    summary_cache: Dict[str, str] = {}
    for source, cat_map in new_by_source.items():
        for cat, papers in cat_map.items():
            for p in papers:
                title = p.get('title', '')
                abstract = p.get('summary', '')
                key = f"{title}||{abstract}"
                if key in summary_cache:
                    final_summary = summary_cache[key]
                else:
                    llm_text = generate_llm_summary(title, abstract, cat) if use_llm_summary else None
                    final_summary = llm_text or fallback_summary(title, abstract, cat)
                    summary_cache[key] = final_summary

                cards.append({
                    'id': paper_key(p),
                    'title': title,
                    'authors': p.get('authors', []) or [],
                    'affiliations': p.get('affiliations', []) or [],
                    'abstract': abstract,
                    'summary': final_summary,
                    'source': source,
                    'category': cat,
                    'url': p.get('url', ''),
                    'pdf_url': p.get('pdf_url', ''),
                })

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding='utf-8')

    out_js.parent.mkdir(parents=True, exist_ok=True)
    out_js.write_text(
        "import cards from './papers.generated.json';\n\nexport const papers = cards;\n",
        encoding='utf-8',
    )


def generate_feishu_message(new_by_source: Dict[str, Dict[str, List[Dict]]], pdf_folder: Path, state_file: Path, dedup_days: int | None, reset_dedup: bool) -> str:
    today = datetime.now().strftime('%Y-%m-%d')

    total_new = sum(
        len(papers)
        for source_map in new_by_source.values()
        for papers in source_map.values()
    )

    lines = [
        f'📚 AI Daily Papers - {today}',
        '',
        f'本次新增论文：{total_new} 篇（相对上次运行去重）',
        f'PDF目录：`{pdf_folder}`',
        f'去重状态文件：`{state_file}`',
        f"去重窗口：{'永久' if dedup_days is None else f'最近 {dedup_days} 天'}",
        f"本次模式：{'重置去重（全量重新判定）' if reset_dedup else '正常增量'}",
        '',
    ]

    lines.extend(format_source_block('ArXiv', new_by_source.get('arxiv', init_bucket())))
    lines.extend(format_source_block('OpenReview', new_by_source.get('openreview', init_bucket())))
    lines.extend(format_source_block('HuggingFace Daily/Trending', new_by_source.get('huggingface', init_bucket())))

    if total_new == 0:
        lines.append('✅ 今天没有新增命中论文。')

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Fetch papers, dedup vs previous run, and download PDFs')
    parser.add_argument(
        '--pdf-dir',
        type=str,
        default='/Users/a123456/.openclaw/workspace/skills/ai-rs-daily-papers/pdfs',
        help='Directory for PDF downloads',
    )
    parser.add_argument('--max-papers', type=int, default=10, help='Maximum papers per category per source')
    parser.add_argument(
        '--state-file',
        type=str,
        default='/Users/a123456/.openclaw/workspace/skills/ai-rs-daily-papers/state/sent_ids.json',
        help='Persistent state file for sent paper IDs',
    )
    parser.add_argument(
        '--reset-dedup',
        action='store_true',
        help='Ignore and reset dedup history for this run (treat as first run)',
    )
    parser.add_argument(
        '--dedup-days',
        type=int,
        default=None,
        help='Only deduplicate against papers sent in last N days',
    )
    parser.add_argument(
        '--no-llm-summary',
        action='store_true',
        help='Disable LLM summary generation and use fallback summary only',
    )
    parser.add_argument(
        '--days',
        type=int,
        default=1,
        help='HuggingFace daily fetch window (N days, default: 1)',
    )
    args = parser.parse_args()

    if args.dedup_days is not None and args.dedup_days <= 0:
        raise ValueError('--dedup-days must be a positive integer')

    today = datetime.now().strftime('%Y-%m-%d')
    pdf_folder = Path(args.pdf_dir) / today
    state_file = Path(args.state_file)

    if not args.no_llm_summary and not LLM_API_KEY:
        print('LLM API key not found, fallback summaries will be used.', file=sys.stderr)

    by_source = fetch_all_sources(args.max_papers, hf_days=max(1, args.days))

    state = load_state(state_file)

    if args.reset_dedup:
        sent_ids = set()
        sent_map = {}
    else:
        sent_map = prune_sent_map(state.get('sent_map', {}), args.dedup_days)
        if not sent_map and state.get('sent_ids'):
            # backward compatibility: old state only had sent_ids (no timestamp)
            if args.dedup_days is None:
                sent_ids = set(state.get('sent_ids', []))
            else:
                sent_ids = set()
        else:
            sent_ids = set(sent_map.keys())

    new_by_source, run_ids = filter_new_only(by_source, sent_ids)

    print(f'Found {len(run_ids)} candidates this run; checking against history...')
    downloaded_count = download_new_pdfs(new_by_source, pdf_folder)
    print(f'Downloaded/linked {downloaded_count} PDFs for newly discovered papers.')

    now_iso = datetime.now().isoformat()
    for rid in run_ids:
        sent_map[rid] = now_iso

    state = {
        'updated_at': now_iso,
        'sent_ids': sorted(sent_map.keys()),
        'sent_map': sent_map,
    }
    save_state(state_file, state)

    message = generate_feishu_message(new_by_source, pdf_folder, state_file, args.dedup_days, args.reset_dedup)
    msg_file = pdf_folder / 'message.txt'
    msg_file.parent.mkdir(parents=True, exist_ok=True)
    msg_file.write_text(message, encoding='utf-8')

    app_json = Path('/Users/a123456/.openclaw/workspace/apps/paper-cards-mvp/src/data/papers.generated.json')
    app_js = Path('/Users/a123456/.openclaw/workspace/apps/paper-cards-mvp/src/data/papers.feed.js')
    export_app_feed(new_by_source, app_json, app_js, use_llm_summary=not args.no_llm_summary)

    print('\n' + '=' * 60)
    print('Message ready for Feishu:')
    print('=' * 60)
    print(message)
    print('=' * 60)
    print(f'\nMessage saved to: {msg_file}')

    return message


if __name__ == '__main__':
    result = main()
    print(result)
