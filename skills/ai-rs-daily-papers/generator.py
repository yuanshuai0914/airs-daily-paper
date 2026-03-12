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
from datetime import datetime
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

ARXIV_NS = {'atom': 'http://www.w3.org/2005/Atom'}


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
            
            papers.append({
                'id': arxiv_id,
                'title': title.text.strip().replace('\n', ' '),
                'summary': (summary.text.strip()[:300] + '...') if summary and len(summary.text.strip()) > 300 else (summary.text.strip() if summary else ''),
                'upvotes': 'N/A',
                'source': 'arxiv',
                'url': f'https://arxiv.org/abs/{arxiv_id}',
                'pdf_url': f'https://arxiv.org/pdf/{arxiv_id}.pdf'
            })
    except Exception as e:
        print(f"Error fetching arxiv: {e}", file=sys.stderr)
    
    return papers


# ==================== OpenReview Fetcher ====================
# Supporting multiple venues: ICLR, NeurIPS, CVPR, ICML, ECCV, AAAI

OPENREVIEW_API_BASE = 'https://api2.openreview.net'

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


def fetch_openreview_notes(invitation: str, limit: int = 100) -> List[Dict]:
    """Fetch notes from OpenReview API."""
    url = f'{OPENREVIEW_API_BASE}/notes?invitation={invitation}&limit={limit}'
    papers = []

    try:
        opener = get_opener()
        req = urllib.request.Request(url, headers={'User-Agent': 'AI-RSDailyPapers/1.0'})
        with opener.open(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        for note in data.get('notes', []):
            content = note.get('content', {})
            title = content.get('title', '') if isinstance(content.get('title'), str) else content.get('title', {}).get('value', '')
            abstract = content.get('abstract', '') if isinstance(content.get('abstract'), str) else content.get('abstract', {}).get('value', '')
            forum_id = note.get('forum', note.get('id', ''))

            papers.append({
                'id': note.get('id', ''),
                'title': title,
                'summary': abstract[:300] + '...' if len(abstract) > 300 else abstract,
                'upvotes': str(note.get('tcdate', 'N/A')),
                'source': 'openreview',
                'url': f'https://openreview.net/forum?id={forum_id}',
                'pdf_url': f'https://openreview.net/pdf?id={forum_id}'
            })
    except Exception as e:
        print(f"Error fetching openreview {invitation}: {e}", file=sys.stderr)

    return papers


def fetch_openreview_all() -> List[Dict]:
    """Fetch all openreview papers from configured invitations."""
    all_papers = []
    seen_ids = set()

    for invitation in OPENREVIEW_INVITATIONS:
        papers = fetch_openreview_notes(invitation, limit=50)
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


def classify_paper(title: str, summary: str) -> Optional[str]:
    """Classify paper into category or None."""
    text = (title + ' ' + summary).lower()

    rs_score = sum(1 for kw in RS_KEYWORDS if kw.lower() in text)
    wm_score = sum(1 for kw in WM_KEYWORDS if kw.lower() in text)
    mm_score = sum(1 for kw in MULTIMODAL_KEYWORDS if kw.lower() in text)
    agent_score = sum(1 for kw in AGENT_KEYWORDS if kw.lower() in text)

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
    
    for arg in sys.argv[1:]:
        if arg == '--compact':
            compact_mode = True
        elif arg.startswith('--output='):
            output_path = arg.split('=', 1)[1]
        elif not arg.startswith('--'):
            output_path = arg
    
    print("Fetching papers from arxiv...")
    arxiv_rs = fetch_arxiv_papers(ARXIV_RS_QUERY)
    arxiv_wm = fetch_arxiv_papers(ARXIV_WM_QUERY)
    arxiv_mm = fetch_arxiv_papers(ARXIV_MULTIMODAL_QUERY)
    arxiv_agent = fetch_arxiv_papers(ARXIV_AGENT_QUERY)

    print("Fetching papers from openreview...")
    openreview_papers = fetch_openreview_all()

    # Combine and deduplicate
    all_papers_raw = arxiv_rs + arxiv_wm + arxiv_mm + arxiv_agent + openreview_papers
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
