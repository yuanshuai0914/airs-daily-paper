#!/usr/bin/env python3
"""
AI RS Daily Papers Generator
Fetches papers from arxiv and openreview, filters by topics.
"""

import os
import sys
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from xml.etree import ElementTree as ET

# Optional proxy support
PROXY = os.environ.get('AI_RS_DAILY_PAPERS_PROXY')

def get_opener():
    """Get urllib opener with optional proxy."""
    if PROXY:
        proxy_handler = urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})
        return urllib.request.build_opener(proxy_handler)
    return urllib.request.build_opener()


# ==================== ArXiv Fetcher ====================

ARXIV_RS_QUERY = (
    'search_query=cat:cs.CV+AND+('
    'remote+sensing+OR+satellite+OR+earth+observation+OR+hyperspectral+OR+SAR'
    ')&sortBy=submittedDate&sortOrder=descending&max_results=20'
)

ARXIV_WM_QUERY = (
    'search_query=cat:cs.CV+AND+('
    'world+model+OR+video+generation+OR+diffusion+model+OR+generative+model'
    ')&sortBy=submittedDate&sortOrder=descending&max_results=20'
)

ARXIV_MULTIMODAL_QUERY = (
    'search_query=(cat:cs.CV+OR+cat:cs.CL+OR+cat:cs.AI)+AND+('
    'multimodal+OR+vision-language+OR+vlm+OR+vision+language+OR+text-image'
    ')&sortBy=submittedDate&sortOrder=descending&max_results=20'
)

ARXIV_AGENT_QUERY = (
    'search_query=cat:cs.AI+AND+('
    'agent+OR+agentic+OR+llm+agent+OR+autonomous+agent+OR+tool+use+OR+planning'
    ')&sortBy=submittedDate&sortOrder=descending&max_results=20'
)

ARXIV_NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'arxiv': 'http://arxiv.org/schemas/atom',
}


def fetch_arxiv_papers(query: str) -> List[Dict]:
    """Fetch papers from arxiv API."""
    url = f'http://export.arxiv.org/api/query?{query}'
    papers = []
    
    try:
        opener = get_opener()
        req = urllib.request.Request(url, headers={'User-Agent': 'AI-RSDailyPapers/1.0'})
        with opener.open(req, timeout=30) as resp:
            data = resp.read()
        
        root = ET.fromstring(data)
        for entry in root.findall('atom:entry', ARXIV_NS):
            paper_id = entry.find('atom:id', ARXIV_NS)
            title = entry.find('atom:title', ARXIV_NS)
            summary = entry.find('atom:summary', ARXIV_NS)
            
            if paper_id is None or title is None:
                continue
            
            # Extract arxiv ID from URL
            id_text = paper_id.text
            arxiv_id_match = re.search(r'arxiv\.org/abs/([\w.]+)', id_text)
            arxiv_id = arxiv_id_match.group(1) if arxiv_id_match else id_text.split('/')[-1]
            
            authors = []
            affiliations = []
            for a in entry.findall('atom:author', ARXIV_NS):
                name_el = a.find('atom:name', ARXIV_NS)
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())
                aff_el = a.find('arxiv:affiliation', ARXIV_NS)
                if aff_el is not None and aff_el.text:
                    affiliations.append(aff_el.text.strip())

            # preserve order while deduplicating affiliations
            affiliations = list(dict.fromkeys(affiliations))

            papers.append({
                'id': arxiv_id,
                'title': title.text.strip().replace('\n', ' '),
                'summary': (summary.text.strip()[:300] + '...') if summary and len(summary.text.strip()) > 300 else (summary.text.strip() if summary else ''),
                'authors': authors,
                'affiliations': affiliations,
                'upvotes': 'N/A',
                'source': 'arxiv',
                'url': f'https://arxiv.org/abs/{arxiv_id}',
                'pdf_url': f'https://arxiv.org/pdf/{arxiv_id}.pdf'
            })
    except Exception as e:
        print(f"Error fetching arxiv: {e}", file=sys.stderr)
    
    return papers


# ==================== HuggingFace Daily Papers Fetcher ====================


def _parse_hf_item(item: Dict, source: str) -> Optional[Dict]:
    """Parse one HuggingFace daily_papers item into our unified schema."""
    paper = item.get('paper', {}) if isinstance(item, dict) else {}
    arxiv_id = paper.get('id', '')
    if not arxiv_id:
        return None

    authors_raw = paper.get('authors', [])
    authors: List[str] = []
    if isinstance(authors_raw, list):
        for a in authors_raw:
            if isinstance(a, dict):
                name = a.get('name', '')
                if name:
                    authors.append(name)
            elif isinstance(a, str) and a:
                authors.append(a)

    upvotes = int(paper.get('upvotes', 0) or 0)
    summary = paper.get('summary', '') or ''

    return {
        'id': arxiv_id,
        'title': (paper.get('title', '') or '').strip(),
        'summary': summary[:300] + '...' if len(summary) > 300 else summary,
        'authors': authors,
        'affiliations': [],
        'upvotes': str(upvotes),
        'source': source,
        'url': f'https://arxiv.org/abs/{arxiv_id}',
        'pdf_url': f'https://arxiv.org/pdf/{arxiv_id}.pdf',
        '_hf_upvotes': upvotes,
    }


def fetch_hf_papers(days: int = 1) -> List[Dict]:
    """Fetch papers from HuggingFace daily + trending endpoints."""
    papers: Dict[str, Dict] = {}
    opener = get_opener()

    days = max(1, int(days or 1))
    today = datetime.now().date()

    # 1) hf-daily (by date)
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        endpoint = f'https://huggingface.co/api/daily_papers?date={d}&limit=100'
        try:
            req = urllib.request.Request(endpoint, headers={'User-Agent': 'AI-RSDailyPapers/1.0'})
            with opener.open(req, timeout=30) as resp:
                items = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            # If date endpoint fails (e.g. future/simulated date), fallback once to default daily endpoint
            if i == 0:
                try:
                    fallback = 'https://huggingface.co/api/daily_papers?limit=100'
                    req = urllib.request.Request(fallback, headers={'User-Agent': 'AI-RSDailyPapers/1.0'})
                    with opener.open(req, timeout=30) as resp:
                        items = json.loads(resp.read().decode('utf-8'))
                    print(f"hf-daily date endpoint failed for {d}, fallback to latest daily list", file=sys.stderr)
                except Exception as e2:
                    print(f"Error fetching hf-daily {d}: {e}; fallback failed: {e2}", file=sys.stderr)
                    items = []
            else:
                print(f"Error fetching hf-daily {d}: {e}", file=sys.stderr)
                items = []

        for item in items if isinstance(items, list) else []:
            p = _parse_hf_item(item, 'hf-daily')
            if not p:
                continue
            if p['id'] not in papers:
                papers[p['id']] = p

    # 2) hf-trending (global)
    endpoint = 'https://huggingface.co/api/daily_papers?sort=trending&limit=100'
    try:
        req = urllib.request.Request(endpoint, headers={'User-Agent': 'AI-RSDailyPapers/1.0'})
        with opener.open(req, timeout=30) as resp:
            items = json.loads(resp.read().decode('utf-8'))
        for item in items if isinstance(items, list) else []:
            p = _parse_hf_item(item, 'hf-trending')
            if not p:
                continue
            old = papers.get(p['id'])
            if old is None or int(p.get('_hf_upvotes', 0)) > int(old.get('_hf_upvotes', 0)):
                papers[p['id']] = p
    except Exception as e:
        print(f"Error fetching hf-trending: {e}", file=sys.stderr)

    return list(papers.values())


# ==================== OpenReview Fetcher ====================
# Supporting multiple venues: ICLR, NeurIPS, CVPR, ICML, ECCV, AAAI

OPENREVIEW_API_BASES = [
    'https://api2.openreview.net',
    'https://api.openreview.net',
]

# NOTE:
# - OpenReview API v1 + Blind_Submission invitations often return empty on public endpoints.
# - We use API v2 with Submission invitations for better public coverage.
OPENREVIEW_INVITATIONS = [
    # ICLR
    'ICLR.cc/2026/Conference/-/Submission',
    'ICLR.cc/2025/Conference/-/Submission',
    'ICLR.cc/2024/Conference/-/Submission',
    # NeurIPS
    'NeurIPS.cc/2025/Conference/-/Submission',
    'NeurIPS.cc/2024/Conference/-/Submission',
    # CVPR
    'thecvf.com/CVPR/2025/Conference/-/Submission',
    'thecvf.com/CVPR/2024/Conference/-/Submission',
    # ICML
    'ICML.cc/2025/Conference/-/Submission',
    'ICML.cc/2024/Conference/-/Submission',
    # ECCV
    'thecvf.com/ECCV/2024/Conference/-/Submission',
    # AAAI
    'AAAI.org/2025/Conference/-/Submission',
]


def fetch_openreview_notes(invitation: str, limit: int = 100, api_base: str = 'https://api2.openreview.net') -> List[Dict]:
    """Fetch notes from OpenReview API."""
    url = f'{api_base}/notes?invitation={invitation}&limit={limit}'
    papers = []

    opener = get_opener()
    req = urllib.request.Request(url, headers={'User-Agent': 'AI-RSDailyPapers/1.0'})
    with opener.open(req, timeout=30) as resp:
        data = json.loads(resp.read().decode('utf-8'))

    for note in data.get('notes', []):
        content = note.get('content', {})
        title = content.get('title', '') if isinstance(content.get('title'), str) else content.get('title', {}).get('value', '')
        abstract = content.get('abstract', '') if isinstance(content.get('abstract'), str) else content.get('abstract', {}).get('value', '')
        forum_id = note.get('forum', note.get('id', ''))

        authors_value = content.get('authors', [])
        if isinstance(authors_value, dict):
            authors_value = authors_value.get('value', [])
        if not isinstance(authors_value, list):
            authors_value = []

        papers.append({
            'id': note.get('id', ''),
            'title': title,
            'summary': abstract[:300] + '...' if len(abstract) > 300 else abstract,
            'authors': [str(x) for x in authors_value],
            'affiliations': [],
            'upvotes': str(note.get('tcdate', 'N/A')),
            'source': 'openreview',
            'url': f'https://openreview.net/forum?id={forum_id}',
            'pdf_url': f'https://openreview.net/pdf?id={forum_id}'
        })

    return papers


def fetch_openreview_all() -> List[Dict]:
    """Fetch all openreview papers with API base fallback and graceful 403 handling."""
    all_papers = []
    seen_ids = set()

    selected_api = None
    last_err = None
    probe_invitation = OPENREVIEW_INVITATIONS[0] if OPENREVIEW_INVITATIONS else None

    # 1) Probe available API base (avoid per-invitation noisy 403 logs)
    if probe_invitation:
        for api_base in OPENREVIEW_API_BASES:
            try:
                _ = fetch_openreview_notes(probe_invitation, limit=1, api_base=api_base)
                selected_api = api_base
                break
            except urllib.error.HTTPError as e:
                last_err = e
                continue
            except Exception as e:
                last_err = e
                continue

    if not selected_api:
        print(f"OpenReview source unavailable (fallback to arXiv + HF only): {last_err}", file=sys.stderr)
        return []

    # 2) Fetch all invitations from selected API base
    for invitation in OPENREVIEW_INVITATIONS:
        try:
            papers = fetch_openreview_notes(invitation, limit=50, api_base=selected_api)
        except Exception as e:
            print(f"Error fetching openreview {invitation} via {selected_api}: {e}", file=sys.stderr)
            continue

        for p in papers:
            if p['id'] not in seen_ids:
                seen_ids.add(p['id'])
                all_papers.append(p)

    return all_papers


# ==================== Filtering ====================

RS_KEYWORDS = [
    'remote sensing', 'satellite', 'earth observation', 'hyperspectral', 'SAR',
    'landsat', 'sentinel', 'aerial', 'geospatial', 'multispectral', 'crop',
    'deforestation', 'urban', 'building extraction', 'change detection'
]

RS_HARD_KEYWORDS = [
    'remote sensing',
    'earth observation',
    'satellite imagery',
    'satellite image',
    'aerial imagery',
    'hyperspectral',
    'multispectral',
    'sar',
]

RS_NEGATIVE_KEYWORDS = [
    'code generation',
    'program synthesis',
    'compiler',
    'jailbreak',
    'instruction tuning',
    'llm alignment',
    'job shop scheduling',
    'fjsp',
    'theorem proving',
    'formal verification',
]

WM_KEYWORDS = [
    'world model', 'video generation', 'video prediction', 'diffusion',
    'generative', 'sora', 'video synthesis', 'temporal modeling',
    'next frame prediction', 'video diffusion', 'latent diffusion'
]

MULTIMODAL_KEYWORDS = [
    'multimodal', 'multi-modal', 'vision-language', 'vision language',
    'vlm', 'mllm', 'vision-language model', 'text-image', 'image-text',
    'image captioning', 'cross-modal', 'cross modal', 'audio-visual'
]

AGENT_KEYWORDS = [
    'agent', 'agentic', 'ai agent', 'llm agent', 'autonomous agent',
    'multi-agent', 'tool use', 'tool-use', 'planning', 'reasoning and acting',
    'react', 'crew', 'workflow agent', 'task planning', 'memory agent'
]


def keyword_hit(text: str, keyword: str) -> bool:
    """Keyword matching with boundary-aware regex to avoid substring false positives (e.g., SAR in adverSARial)."""
    kw = keyword.strip().lower()
    if not kw:
        return False

    # Build phrase pattern: remote sensing -> \bremote\s+sensing\b
    parts = [re.escape(p) for p in kw.split() if p]
    if not parts:
        return False
    pattern = r'\b' + r'\s+'.join(parts) + r'\b'
    return re.search(pattern, text) is not None


def rs_hard_match(text: str) -> bool:
    if any(keyword_hit(text, kw) for kw in RS_HARD_KEYWORDS):
        return True
    # geospatial must co-occur with image/vision/mapping signal
    return keyword_hit(text, 'geospatial') and (
        keyword_hit(text, 'image') or keyword_hit(text, 'vision') or keyword_hit(text, 'mapping')
    )


def rs_negative_match(text: str) -> bool:
    return any(keyword_hit(text, kw) for kw in RS_NEGATIVE_KEYWORDS)


def classify_paper(title: str, summary: str) -> Optional[str]:
    """Classify paper into category or None."""
    text = (title + ' ' + summary).lower()

    rs_score_raw = sum(1 for kw in RS_KEYWORDS if keyword_hit(text, kw))
    rs_score = rs_score_raw if (rs_hard_match(text) and not rs_negative_match(text)) else 0

    wm_score = sum(1 for kw in WM_KEYWORDS if keyword_hit(text, kw))
    mm_score = sum(1 for kw in MULTIMODAL_KEYWORDS if keyword_hit(text, kw))
    agent_score = sum(1 for kw in AGENT_KEYWORDS if keyword_hit(text, kw))

    scores = {
        'rs': rs_score,
        'wm': wm_score,
        'mm': mm_score,
        'agent': agent_score
    }
    best_cat = max(scores, key=scores.get)
    if scores[best_cat] <= 0:
        return None
    return best_cat


def relevance_score(title: str, summary: str, source: str = '', upvotes: int = 0) -> int:
    """Unified ranking score used after classification (merged from airs fetch logic)."""
    text = (title + ' ' + summary).lower()
    title_lower = title.lower()

    rs_score_raw = sum(1 for kw in RS_KEYWORDS if keyword_hit(text, kw))
    rs_score = rs_score_raw if (rs_hard_match(text) and not rs_negative_match(text)) else 0
    wm_score = sum(1 for kw in WM_KEYWORDS if keyword_hit(text, kw))
    mm_score = sum(1 for kw in MULTIMODAL_KEYWORDS if keyword_hit(text, kw))
    agent_score = sum(1 for kw in AGENT_KEYWORDS if keyword_hit(text, kw))

    base = max(rs_score, wm_score, mm_score, agent_score)

    # title hit boost
    title_boost = 0
    for kw in RS_KEYWORDS + WM_KEYWORDS + MULTIMODAL_KEYWORDS + AGENT_KEYWORDS:
        if keyword_hit(title_lower, kw):
            title_boost += 1

    score = base * 2 + min(title_boost, 3)

    # trending boost (inspired by airs-daily-paper fetch logic)
    if source == 'hf-trending':
        if upvotes >= 10:
            score += 3
        elif upvotes >= 5:
            score += 2
        elif upvotes >= 2:
            score += 1

    return score


# ==================== Report Generation ====================

def generate_markdown_report(rs_papers: List[Dict], wm_papers: List[Dict], mm_papers: List[Dict], agent_papers: List[Dict], output_path: str):
    """Generate markdown report."""
    today = datetime.now().strftime('%Y-%m-%d')

    lines = [
        f'# AI Daily Papers - {today}',
        '',
        f'> Auto-generated report with {len(rs_papers)} Remote Sensing papers, {len(wm_papers)} World Model papers, {len(mm_papers)} Multimodal papers, and {len(agent_papers)} Agent papers',
        '',
        '---',
        '',
        '## 🛰️ Remote Sensing (Satellite, Earth Observation)',
        ''
    ]
    
    for i, p in enumerate(rs_papers[:15], 1):
        pdf_link = f" | [PDF]({p['pdf_url']})" if 'pdf_url' in p else ""
        lines.extend([
            f"### {i}. {p['title']}",
            '',
            f"- **Source:** {p['source']} | **Upvotes:** {p['upvotes']}{pdf_link}",
            f"- **ID:** `{p['id']}`",
            f"- **URL:** {p['url']}",
            '',
            f"> {p['summary']}" if p['summary'] else "",
            ''
        ])
    
    lines.extend([
        '---',
        '',
        '## 🌍 World Model (Generation, Video, Diffusion)',
        ''
    ])

    for i, p in enumerate(wm_papers[:15], 1):
        pdf_link = f" | [PDF]({p['pdf_url']})" if 'pdf_url' in p else ""
        lines.extend([
            f"### {i}. {p['title']}",
            '',
            f"- **Source:** {p['source']} | **Upvotes:** {p['upvotes']}{pdf_link}",
            f"- **ID:** `{p['id']}`",
            f"- **URL:** {p['url']}",
            '',
            f"> {p['summary']}" if p['summary'] else "",
            ''
        ])

    lines.extend([
        '---',
        '',
        '## 🧩 Multimodal (Vision-Language, MLLM)',
        ''
    ])

    for i, p in enumerate(mm_papers[:15], 1):
        pdf_link = f" | [PDF]({p['pdf_url']})" if 'pdf_url' in p else ""
        lines.extend([
            f"### {i}. {p['title']}",
            '',
            f"- **Source:** {p['source']} | **Upvotes:** {p['upvotes']}{pdf_link}",
            f"- **ID:** `{p['id']}`",
            f"- **URL:** {p['url']}",
            '',
            f"> {p['summary']}" if p['summary'] else "",
            ''
        ])

    lines.extend([
        '---',
        '',
        '## 🤖 Agent (Agentic AI, LLM Agents, Tool Use)',
        ''
    ])

    for i, p in enumerate(agent_papers[:15], 1):
        pdf_link = f" | [PDF]({p['pdf_url']})" if 'pdf_url' in p else ""
        lines.extend([
            f"### {i}. {p['title']}",
            '',
            f"- **Source:** {p['source']} | **Upvotes:** {p['upvotes']}{pdf_link}",
            f"- **ID:** `{p['id']}`",
            f"- **URL:** {p['url']}",
            '',
            f"> {p['summary']}" if p['summary'] else "",
            ''
        ])

    lines.extend([
        '---',
        '',
        f'*Generated on {today} by ai-rs-daily-papers*'
    ])
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"Report saved to: {output_path}")


def generate_compact_summary(rs_papers: List[Dict], wm_papers: List[Dict], mm_papers: List[Dict], agent_papers: List[Dict]) -> str:
    """Generate compact summary for Feishu message."""
    today = datetime.now().strftime('%Y-%m-%d')

    lines = [f'📚 AI Daily Papers - {today}', '']

    lines.append('🛰️ Remote Sensing:')
    for i, p in enumerate(rs_papers[:5], 1):
        title = p['title'][:50] + '...' if len(p['title']) > 50 else p['title']
        pdf_link = f" | [PDF]({p.get('pdf_url', '')})" if 'pdf_url' in p else ""
        lines.append(f"{i}. {title} ({p['source']}){pdf_link}")

    lines.append('')
    lines.append('🌍 World Model:')
    for i, p in enumerate(wm_papers[:5], 1):
        title = p['title'][:50] + '...' if len(p['title']) > 50 else p['title']
        pdf_link = f" | [PDF]({p.get('pdf_url', '')})" if 'pdf_url' in p else ""
        lines.append(f"{i}. {title} ({p['source']}){pdf_link}")

    lines.append('')
    lines.append('🧩 Multimodal:')
    for i, p in enumerate(mm_papers[:5], 1):
        title = p['title'][:50] + '...' if len(p['title']) > 50 else p['title']
        pdf_link = f" | [PDF]({p.get('pdf_url', '')})" if 'pdf_url' in p else ""
        lines.append(f"{i}. {title} ({p['source']}){pdf_link}")

    lines.append('')
    lines.append('🤖 Agent:')
    for i, p in enumerate(agent_papers[:5], 1):
        title = p['title'][:50] + '...' if len(p['title']) > 50 else p['title']
        pdf_link = f" | [PDF]({p.get('pdf_url', '')})" if 'pdf_url' in p else ""
        lines.append(f"{i}. {title} ({p['source']}){pdf_link}")

    return '\n'.join(lines)


# ==================== Main ====================

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Default output to recommendations folder
    default_output = os.path.join(script_dir, 'recommendations', datetime.now().strftime('%Y-%m-%d') + '.md')

    # Parse args
    output_path = default_output
    compact_mode = False
    days = 1

    for arg in sys.argv[1:]:
        if arg == '--compact':
            compact_mode = True
        elif arg.startswith('--output='):
            output_path = arg.split('=', 1)[1]
        elif arg.startswith('--days='):
            try:
                days = max(1, int(arg.split('=', 1)[1]))
            except Exception:
                days = 1
        elif not arg.startswith('--'):
            output_path = arg

    print("Fetching papers from arxiv...")
    arxiv_rs = fetch_arxiv_papers(ARXIV_RS_QUERY)
    arxiv_wm = fetch_arxiv_papers(ARXIV_WM_QUERY)
    arxiv_mm = fetch_arxiv_papers(ARXIV_MULTIMODAL_QUERY)
    arxiv_agent = fetch_arxiv_papers(ARXIV_AGENT_QUERY)

    print("Fetching papers from openreview...")
    openreview_papers = fetch_openreview_all()

    print(f"Fetching papers from huggingface (days={days})...")
    hf_papers = fetch_hf_papers(days=days)

    # Combine and deduplicate
    all_papers_raw = arxiv_rs + arxiv_wm + arxiv_mm + arxiv_agent + openreview_papers + hf_papers
    all_papers = []
    seen_ids = set()
    for p in all_papers_raw:
        if p['id'] not in seen_ids:
            seen_ids.add(p['id'])
            all_papers.append(p)

    rs_papers = []
    wm_papers = []
    mm_papers = []
    agent_papers = []

    # score first, then classify + select
    for p in all_papers:
        p['_score'] = relevance_score(
            p.get('title', ''),
            p.get('summary', ''),
            p.get('source', ''),
            int(p.get('_hf_upvotes', 0) or 0),
        )

    all_papers.sort(key=lambda x: x.get('_score', 0), reverse=True)

    for p in all_papers:
        cat = classify_paper(p['title'], p['summary'])
        if cat == 'rs' and len(rs_papers) < 15:
            rs_papers.append(p)
        elif cat == 'wm' and len(wm_papers) < 15:
            wm_papers.append(p)
        elif cat == 'mm' and len(mm_papers) < 15:
            mm_papers.append(p)
        elif cat == 'agent' and len(agent_papers) < 15:
            agent_papers.append(p)

    print(f"Found {len(rs_papers)} RS papers, {len(wm_papers)} WM papers, {len(mm_papers)} Multimodal papers, {len(agent_papers)} Agent papers")

    if compact_mode:
        print(generate_compact_summary(rs_papers, wm_papers, mm_papers, agent_papers))
    else:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        generate_markdown_report(rs_papers, wm_papers, mm_papers, agent_papers, output_path)

    return 0


if __name__ == '__main__':
    sys.exit(main())
