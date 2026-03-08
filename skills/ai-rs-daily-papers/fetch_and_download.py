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
from typing import Dict, List, Tuple
from datetime import datetime

# Import from generator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generator import (
    fetch_arxiv_papers,
    ARXIV_RS_QUERY,
    ARXIV_WM_QUERY,
    ARXIV_MULTIMODAL_QUERY,
    ARXIV_AGENT_QUERY,
    fetch_openreview_all,
    classify_paper,
)

PROXY = os.environ.get('AI_RS_DAILY_PAPERS_PROXY')

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


def load_sent_ids(state_file: Path) -> set:
    if not state_file.exists():
        return set()
    try:
        data = json.loads(state_file.read_text(encoding='utf-8'))
        return set(data.get('sent_ids', []))
    except Exception:
        return set()


def save_sent_ids(state_file: Path, sent_ids: set):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'updated_at': datetime.now().isoformat(),
        'sent_ids': sorted(sent_ids),
    }
    state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


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


def fetch_all_sources(max_per_category: int) -> Dict[str, Dict[str, List[Dict]]]:
    print('Fetching papers from arxiv...')
    arxiv_raw = (
        fetch_arxiv_papers(ARXIV_RS_QUERY)
        + fetch_arxiv_papers(ARXIV_WM_QUERY)
        + fetch_arxiv_papers(ARXIV_MULTIMODAL_QUERY)
        + fetch_arxiv_papers(ARXIV_AGENT_QUERY)
    )

    print('Fetching papers from openreview...')
    openreview_raw = fetch_openreview_all()

    return {
        'arxiv': classify_source_papers(arxiv_raw, max_per_category),
        'openreview': classify_source_papers(openreview_raw, max_per_category),
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


def generate_feishu_message(new_by_source: Dict[str, Dict[str, List[Dict]]], pdf_folder: Path, state_file: Path) -> str:
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
        '',
    ]

    lines.extend(format_source_block('ArXiv', new_by_source.get('arxiv', init_bucket())))
    lines.extend(format_source_block('OpenReview', new_by_source.get('openreview', init_bucket())))

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
    args = parser.parse_args()

    today = datetime.now().strftime('%Y-%m-%d')
    pdf_folder = Path(args.pdf_dir) / today
    state_file = Path(args.state_file)

    by_source = fetch_all_sources(args.max_papers)

    sent_ids = load_sent_ids(state_file)
    new_by_source, run_ids = filter_new_only(by_source, sent_ids)

    print(f'Found {len(run_ids)} candidates this run; checking against history...')
    downloaded_count = download_new_pdfs(new_by_source, pdf_folder)
    print(f'Downloaded/linked {downloaded_count} PDFs for newly discovered papers.')

    # Persist dedup state (union)
    sent_ids.update(run_ids)
    save_sent_ids(state_file, sent_ids)

    message = generate_feishu_message(new_by_source, pdf_folder, state_file)
    msg_file = pdf_folder / 'message.txt'
    msg_file.parent.mkdir(parents=True, exist_ok=True)
    msg_file.write_text(message, encoding='utf-8')

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
