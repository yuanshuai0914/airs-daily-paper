#!/usr/bin/env python3
"""
AI RS Daily Papers - Full Workflow
Fetches papers, downloads PDFs, generates report with download links.
"""

import os
import sys
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

# Import from generator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generator import (
    fetch_arxiv_papers, ARXIV_RS_QUERY, ARXIV_WM_QUERY, ARXIV_MULTIMODAL_QUERY, ARXIV_AGENT_QUERY,
    fetch_openreview_all, classify_paper
)

# Optional proxy support
PROXY = os.environ.get('AI_RS_DAILY_PAPERS_PROXY')

def get_opener():
    """Get urllib opener with optional proxy."""
    if PROXY:
        proxy_handler = urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})
        return urllib.request.build_opener(proxy_handler)
    return urllib.request.build_opener()


def download_file(url: str, output_path: str, timeout: int = 120) -> bool:
    """Download a file from URL to output path."""
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
    """Sanitize title for use as filename."""
    invalid_chars = '<>:"/\\|?*'
    filename = title
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    if len(filename) > max_length:
        filename = filename[:max_length]
    return filename.strip()


def fetch_and_download(output_dir: str, max_papers: int = 10) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict], str]:
    """
    Fetch papers and download PDFs.
    Returns: (rs_papers, wm_papers, mm_papers, agent_papers, pdf_folder_path)
    """
    output_path = Path(output_dir)
    today = datetime.now().strftime('%Y-%m-%d')
    pdf_folder = output_path / today
    pdf_folder.mkdir(parents=True, exist_ok=True)
    
    print("Fetching papers from arxiv...")
    arxiv_rs = fetch_arxiv_papers(ARXIV_RS_QUERY)
    arxiv_wm = fetch_arxiv_papers(ARXIV_WM_QUERY)
    arxiv_mm = fetch_arxiv_papers(ARXIV_MULTIMODAL_QUERY)
    arxiv_agent = fetch_arxiv_papers(ARXIV_AGENT_QUERY)

    print("Fetching papers from openreview...")
    openreview_papers = fetch_openreview_all()

    # Combine and classify
    all_papers = arxiv_rs + arxiv_wm + arxiv_mm + arxiv_agent + openreview_papers

    rs_papers = []
    wm_papers = []
    mm_papers = []
    agent_papers = []
    
    for p in all_papers:
        cat = classify_paper(p['title'], p['summary'])
        if cat == 'rs' and len(rs_papers) < max_papers:
            rs_papers.append(p)
        elif cat == 'wm' and len(wm_papers) < max_papers:
            wm_papers.append(p)
        elif cat == 'mm' and len(mm_papers) < max_papers:
            mm_papers.append(p)
        elif cat == 'agent' and len(agent_papers) < max_papers:
            agent_papers.append(p)
    
    # Download PDFs
    print(f"\nDownloading PDFs to {pdf_folder}...")
    downloaded_count = 0
    
    for paper in rs_papers + wm_papers + mm_papers + agent_papers:
        pdf_url = paper.get('pdf_url')
        if not pdf_url:
            continue
        
        safe_title = sanitize_filename(paper['title'])
        paper_id = paper['id'].replace('/', '_').replace(':', '_')
        filename = f"{paper_id}_{safe_title}.pdf"
        filepath = pdf_folder / filename
        
        if filepath.exists():
            print(f"  ✓ Already exists: {filename}")
            paper['local_pdf'] = str(filepath)
            downloaded_count += 1
            continue
        
        print(f"  Downloading: {filename[:70]}...")
        if download_file(pdf_url, str(filepath)):
            paper['local_pdf'] = str(filepath)
            downloaded_count += 1
            print(f"    ✓ Success")
        else:
            print(f"    ✗ Failed")
    
    print(f"\nDownload complete: {downloaded_count} PDFs in {pdf_folder}")
    return rs_papers, wm_papers, mm_papers, agent_papers, str(pdf_folder)


def generate_feishu_message(rs_papers: List[Dict], wm_papers: List[Dict], mm_papers: List[Dict], agent_papers: List[Dict], pdf_folder: str) -> str:
    """Generate Feishu message with paper list and PDF links."""
    today = datetime.now().strftime('%Y-%m-%d')
    
    lines = [
        f'📚 **AI Daily Papers - {today}**',
        '',
        f'📁 PDF已下载到本地文件夹：`{pdf_folder}`',
        '请手动上传到飞书云盘：https://my.feishu.cn/drive/folder/KcGmfS1y6lRd4gd1ofLclbzSnXc',
        ''
    ]
    
    lines.append('🛰️ **Remote Sensing Papers:**')
    for i, p in enumerate(rs_papers[:8], 1):
        title = p['title'][:55] + '...' if len(p['title']) > 55 else p['title']
        pdf_link = p.get('pdf_url', '')
        local_file = Path(p.get('local_pdf', '')).name if 'local_pdf' in p else '未下载'
        lines.append(f"{i}. {title}")
        lines.append(f"   📄 {local_file}")
        lines.append(f"   🔗 [PDF链接]({pdf_link})")
        lines.append('')
    
    lines.append('🌍 **World Model Papers:**')
    for i, p in enumerate(wm_papers[:8], 1):
        title = p['title'][:55] + '...' if len(p['title']) > 55 else p['title']
        pdf_link = p.get('pdf_url', '')
        local_file = Path(p.get('local_pdf', '')).name if 'local_pdf' in p else '未下载'
        lines.append(f"{i}. {title}")
        lines.append(f"   📄 {local_file}")
        lines.append(f"   🔗 [PDF链接]({pdf_link})")
        lines.append('')
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Fetch papers and download PDFs')
    parser.add_argument('--pdf-dir', type=str, 
                        default='/Users/a123456/.openclaw/workspace/skills/ai-rs-daily-papers/pdfs',
                        help='Directory for PDF downloads')
    parser.add_argument('--max-papers', type=int, default=10,
                        help='Maximum papers per category')
    args = parser.parse_args()
    
    # Fetch and download
    rs_papers, wm_papers, mm_papers, agent_papers, pdf_folder = fetch_and_download(args.pdf_dir, args.max_papers)
    
    # Generate message
    message = generate_feishu_message(rs_papers, wm_papers, mm_papers, agent_papers, pdf_folder)
    
    # Save message to file for sending
    msg_file = Path(pdf_folder) / 'message.txt'
    msg_file.write_text(message, encoding='utf-8')
    
    print(f"\n{'='*60}")
    print("Message ready for Feishu:")
    print(f"{'='*60}")
    print(message)
    print(f"{'='*60}")
    print(f"\nMessage saved to: {msg_file}")
    
    return message


if __name__ == '__main__':
    msg = main()
    # Print to stdout for shell script capture
    print(msg)
