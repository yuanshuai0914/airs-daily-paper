#!/usr/bin/env python3
"""
AI Premium Remote Sensing Papers Fetcher
Fetches papers from Nature, Science, and PNAS related to remote sensing.
"""

import os
import re
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Keywords for filtering
KEYWORDS = ['remote sensing', 'satellite', 'earth observation', 'hyperspectral', 'multispectral', 
            'synthetic aperture radar', 'SAR', 'LiDAR', 'geospatial', 'land cover', 'vegetation index',
            'NDVI', 'thermal infrared', 'atmospheric correction', 'pixel', 'spatial resolution']
KEYWORD_PATTERNS = [re.compile(rf'\b{kw}\b', re.IGNORECASE) for kw in KEYWORDS]

@dataclass
class Paper:
    title: str
    authors: List[str]
    abstract: str
    url: str
    published_date: str
    source: str
    doi: Optional[str] = None
    pdf_url: Optional[str] = None
    
    def to_markdown(self) -> str:
        authors_str = ', '.join(self.authors[:3])
        if len(self.authors) > 3:
            authors_str += ' et al.'
        pdf_link = f"\n- **PDF:** [{self.pdf_url}]({self.pdf_url})" if self.pdf_url else ""
        return f"""### [{self.title}]({self.url})
- **Source:** {self.source}
- **Authors:** {authors_str}
- **Published:** {self.published_date}
- **DOI:** {self.doi or 'N/A'}{pdf_link}
- **Abstract:** {self.abstract[:500]}{'...' if len(self.abstract) > 500 else ''}
"""

    def to_compact(self, index: int) -> str:
        """Compact format for Feishu summary."""
        authors_str = ', '.join(self.authors[:2])
        if len(self.authors) > 2:
            authors_str += ' et al.'
        return f"{index}. **{self.title}** ({self.source})\n   👤 {authors_str} | 📅 {self.published_date} | 🔗 [链接]({self.url})"


class BaseFetcher:
    """Base class for paper fetchers."""
    
    def __init__(self, api_key: Optional[str] = None, proxy: Optional[str] = None):
        self.api_key = api_key
        self.proxy = proxy
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {'http': proxy, 'https': proxy}
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def fetch(self) -> List[Paper]:
        raise NotImplementedError


class NatureFetcher(BaseFetcher):
    """Fetcher for Nature publications."""
    
    # Nature主RSS源
    RSS_URLS = [
        "https://www.nature.com/nature.rss",
        "https://www.nature.com/ncomms.rss",  # Nature Communications
        "https://www.nature.com/srep.rss",    # Scientific Reports
    ]
    
    def fetch(self) -> List[Paper]:
        """Fetch papers from Nature RSS feeds."""
        all_papers = []
        
        for rss_url in self.RSS_URLS:
            try:
                papers = self._fetch_single_rss(rss_url)
                if papers:
                    logger.info(f"Nature ({rss_url.split('/')[-1]}): Fetched {len(papers)} papers")
                    all_papers.extend(papers)
            except Exception as e:
                logger.error(f"Nature fetch failed for {rss_url}: {e}")
        
        # Remove duplicates by DOI
        seen = set()
        unique_papers = []
        for p in all_papers:
            key = p.doi or p.url
            if key and key not in seen:
                seen.add(key)
                unique_papers.append(p)
        
        return unique_papers
    
    def _fetch_single_rss(self, rss_url: str) -> List[Paper]:
        """Fetch from a single Nature RSS feed."""
        response = self.session.get(rss_url, timeout=30)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        papers = []
        
        # Define namespaces for RDF-based RSS
        ns = {
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'prism': 'http://prismstandard.org/namespaces/basic/2.0/',
            'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
            'rss': 'http://purl.org/rss/1.0/'  # RSS 1.0 namespace
        }
        
        # Nature uses RSS 1.0 (RDF format), so items are in rss namespace
        for item in root.findall('.//rss:item', ns):
            title_elem = item.find('rss:title', ns)
            title = title_elem.text if title_elem is not None else ''
            
            link_elem = item.find('rss:link', ns)
            link = link_elem.text if link_elem is not None else ''
            
            # Try dc:date first, then prism:publicationDate
            pub_date = ''
            date_elem = item.find('dc:date', ns)
            if date_elem is not None:
                pub_date = date_elem.text or ''
            
            desc_elem = item.find('rss:description', ns)
            description = desc_elem.text if desc_elem is not None else ''
            
            # Get content encoded if available
            content_encoded = item.find('.//{http://purl.org/rss/1.0/modules/content/}encoded')
            full_text = content_encoded.text if content_encoded is not None else description
            
            # Filter by keywords
            content_text = f"{title} {full_text}".lower()
            if not any(pattern.search(content_text) for pattern in KEYWORD_PATTERNS):
                continue
            
            # Extract authors from dc:creator
            authors = []
            for creator in item.findall('.//dc:creator', ns):
                if creator.text:
                    authors.append(creator.text)
            if not authors:
                authors = ['Nature Research']
            
            # Extract DOI
            doi = None
            doi_elem = item.find('.//dc:identifier', ns)
            if doi_elem is not None and doi_elem.text:
                doi = doi_elem.text.replace('doi:', '')
            elif '/articles/' in link:
                doi = f"10.1038/{link.split('/articles/')[-1].split('/')[-1]}"
            
            # Construct PDF URL
            pdf_url = None
            if doi:
                pdf_url = f"https://www.nature.com/articles/{doi.split('/')[-1]}.pdf"
            
            papers.append(Paper(
                title=title.strip() if title else 'Untitled',
                authors=authors,
                abstract=description.strip() if description else '',
                url=link.strip() if link else '',
                published_date=self._parse_date(pub_date),
                source='Nature',
                doi=doi,
                pdf_url=pdf_url
            ))
        
        return papers
    
    def _parse_date(self, date_str: str) -> str:
        """Parse RSS date format."""
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d')
        try:
            # Try ISO format first
            if 'T' in date_str:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return dt.strftime('%Y-%m-%d')
            # Try common RSS date formats
            for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S GMT', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(date_str.strip(), fmt)
                    return dt.strftime('%Y-%m-%d')
                except:
                    continue
        except:
            pass
        return date_str[:10] if date_str else datetime.now().strftime('%Y-%m-%d')


class ScienceFetcher(BaseFetcher):
    """Fetcher for Science/AAAS publications."""
    
    RSS_URLS = [
        "https://www.science.org/rss/news_current.xml",
    ]
    
    def fetch(self) -> List[Paper]:
        """Fetch papers from Science."""
        papers = []
        try:
            # Try RSS feeds
            for rss_url in self.RSS_URLS:
                try:
                    feed_papers = self._fetch_single_rss(rss_url)
                    papers.extend(feed_papers)
                    logger.info(f"Science ({rss_url.split('/')[-1]}): Fetched {len(feed_papers)} papers")
                except Exception as e:
                    logger.error(f"Science RSS failed for {rss_url}: {e}")
                
        except Exception as e:
            logger.error(f"Science fetch failed: {e}")
        
        return papers
    
    def _fetch_single_rss(self, rss_url: str) -> List[Paper]:
        """Fetch from a single Science RSS feed."""
        response = self.session.get(rss_url, timeout=30)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        papers = []
        
        # Define namespaces
        ns = {
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'prism': 'http://prismstandard.org/namespaces/basic/2.0/',
            'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
        }
        
        for item in root.findall('.//item'):
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            pub_date = item.findtext('.//dc:date', '', ns)
            description = item.findtext('description', '')
            
            # Filter by keywords
            content_text = f"{title} {description}".lower()
            if not any(pattern.search(content_text) for pattern in KEYWORD_PATTERNS):
                continue
            
            # Extract authors from dc:creator
            authors = []
            for creator in item.findall('.//dc:creator', ns):
                if creator.text:
                    authors.append(creator.text)
            if not authors:
                authors = ['Science AAAS']
            
            # Extract DOI from dc:identifier
            doi = None
            doi_elem = item.find('.//dc:identifier', ns)
            if doi_elem is not None and doi_elem.text:
                doi = doi_elem.text.replace('doi:', '')
            
            papers.append(Paper(
                title=title.strip() if title else 'Untitled',
                authors=authors,
                abstract=description.strip() if description else '',
                url=link.strip() if link else '',
                published_date=self._parse_date(pub_date),
                source='Science',
                doi=doi
            ))
        
        return papers
    
    def _parse_date(self, date_str: str) -> str:
        """Parse RSS date format."""
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d')
        try:
            # Try ISO format
            if 'T' in date_str:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return dt.strftime('%Y-%m-%d')
        except:
            pass
        return date_str[:10] if date_str else datetime.now().strftime('%Y-%m-%d')


class PNASFetcher(BaseFetcher):
    """Fetcher for PNAS (Proceedings of the National Academy of Sciences)."""
    
    RSS_URLS = [
        "https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas",
    ]
    
    def fetch(self) -> List[Paper]:
        """Fetch papers from PNAS RSS feeds."""
        papers = []
        errors = []
        
        for rss_url in self.RSS_URLS:
            try:
                feed_papers = self._fetch_single_rss(rss_url)
                papers.extend(feed_papers)
                logger.info(f"PNAS ({rss_url.split('/')[-1]}): Fetched {len(feed_papers)} papers")
            except Exception as e:
                errors.append(f"{rss_url}: {e}")
        
        if errors and not papers:
            logger.error(f"PNAS all feeds failed: {errors}")
        
        # Remove duplicates by DOI/URL
        seen = set()
        unique_papers = []
        for p in papers:
            key = p.doi or p.url
            if key and key not in seen:
                seen.add(key)
                unique_papers.append(p)
        
        return unique_papers
    
    def _fetch_single_rss(self, rss_url: str) -> List[Paper]:
        """Fetch from a single PNAS RSS feed."""
        response = self.session.get(rss_url, timeout=30)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        papers = []
        
        # Define namespaces
        ns = {
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'media': 'http://search.yahoo.com/mrss/',
            'prism': 'http://prismstandard.org/namespaces/basic/2.0/'
        }
        
        for item in root.findall('.//item'):
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            pub_date = item.findtext('pubDate', '')
            description = item.findtext('description', '')
            
            # Filter by keywords
            content_text = f"{title} {description}".lower()
            if not any(pattern.search(content_text) for pattern in KEYWORD_PATTERNS):
                continue
            
            # Extract authors from dc:creator
            authors = []
            for creator in item.findall('.//dc:creator', ns):
                if creator.text:
                    authors.append(creator.text)
            if not authors:
                authors = ['PNAS']
            
            # Extract DOI
            doi = None
            if 'doi.org' in link:
                doi = link.split('doi.org/')[-1].split('?')[0]
            elif 'doi/abs' in link:
                doi = link.split('doi/abs/')[-1].split('?')[0]
            
            # Construct PDF URL
            pdf_url = None
            if doi:
                pdf_url = f"https://www.pnas.org/doi/pdf/{doi}"
            
            papers.append(Paper(
                title=title.strip() if title else 'Untitled',
                authors=authors,
                abstract=description.strip() if description else '',
                url=link.strip() if link else '',
                published_date=self._parse_date(pub_date),
                source='PNAS',
                doi=doi,
                pdf_url=pdf_url
            ))
        
        return papers
    
    def _parse_date(self, date_str: str) -> str:
        """Parse RSS date format."""
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d')
        try:
            dt = datetime.strptime(date_str.split('+')[0].strip(), '%a, %d %b %Y %H:%M:%S')
            return dt.strftime('%Y-%m-%d')
        except:
            return date_str[:10] if date_str else datetime.now().strftime('%Y-%m-%d')


def generate_report(papers: List[Paper], output_dir: Path) -> Path:
    """Generate markdown report."""
    today = datetime.now().strftime('%Y-%m-%d')
    output_file = output_dir / f"{today}.md"
    
    # Sort by date (newest first)
    papers.sort(key=lambda p: p.published_date, reverse=True)
    
    markdown = f"""# Premium Remote Sensing Papers - {today}

> **Sources:** Nature, Science, PNAS  
> **Keywords:** remote sensing, satellite, earth observation, etc.  
> **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary

Total papers found: **{len(papers)}**

| Source | Count |
|--------|-------|
"""
    # Count by source
    source_counts = {}
    for p in papers:
        source_counts[p.source] = source_counts.get(p.source, 0) + 1
    
    for source, count in sorted(source_counts.items()):
        markdown += f"| {source} | {count} |\n"
    
    markdown += "\n---\n\n"
    
    # List all papers
    for paper in papers:
        markdown += paper.to_markdown() + "\n"
    
    output_file.write_text(markdown, encoding='utf-8')
    logger.info(f"Report saved to: {output_file}")
    return output_file


def generate_compact_summary(papers: List[Paper], max_papers: int = 10) -> str:
    """Generate compact summary for Feishu."""
    # Sort by date
    papers.sort(key=lambda p: p.published_date, reverse=True)
    top_papers = papers[:max_papers]
    
    today = datetime.now().strftime('%Y-%m-%d')
    summary = f"📡 **每日遥感顶刊速递** ({today})\n\n"
    
    for i, paper in enumerate(top_papers, 1):
        summary += paper.to_compact(i) + "\n"
    
    if len(papers) > max_papers:
        summary += f"\n... 还有 {len(papers) - max_papers} 篇论文 (详见完整报告)\n"
    
    return summary


def main():
    parser = argparse.ArgumentParser(description='Fetch premium remote sensing papers')
    parser.add_argument('--output-dir', type=Path, default=Path('recommendations'),
                        help='Output directory for reports')
    parser.add_argument('--compact', action='store_true',
                        help='Output compact summary for Feishu')
    parser.add_argument('--max-compact', type=int, default=10,
                        help='Maximum papers in compact summary')
    parser.add_argument('--proxy', type=str, default=os.getenv('AI_PREMIUM_RS_PAPERS_PROXY'),
                        help='HTTP proxy URL')
    args = parser.parse_args()
    
    # Get API keys from environment
    nature_key = os.getenv('NATURE_API_KEY')
    science_key = os.getenv('SCIENCE_API_KEY')
    pnas_key = os.getenv('PNAS_API_KEY')
    
    # Ensure output directory exists
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    all_papers = []
    results = {'success': [], 'failed': []}
    
    # Fetch from Nature
    logger.info("Fetching from Nature...")
    nature = NatureFetcher(api_key=nature_key, proxy=args.proxy)
    nature_papers = nature.fetch()
    if nature_papers:
        all_papers.extend(nature_papers)
        results['success'].append(f"Nature ({len(nature_papers)} papers)")
    else:
        results['failed'].append('Nature')
    
    # Fetch from Science
    logger.info("Fetching from Science...")
    science = ScienceFetcher(api_key=science_key, proxy=args.proxy)
    science_papers = science.fetch()
    if science_papers:
        all_papers.extend(science_papers)
        results['success'].append(f"Science ({len(science_papers)} papers)")
    else:
        results['failed'].append('Science')
    
    # Fetch from PNAS
    logger.info("Fetching from PNAS...")
    pnas = PNASFetcher(api_key=pnas_key, proxy=args.proxy)
    pnas_papers = pnas.fetch()
    if pnas_papers:
        all_papers.extend(pnas_papers)
        results['success'].append(f"PNAS ({len(pnas_papers)} papers)")
    else:
        results['failed'].append('PNAS')
    
    # Log results
    logger.info(f"Results: {len(all_papers)} total papers")
    if results['success']:
        logger.info(f"Success: {', '.join(results['success'])}")
    if results['failed']:
        logger.warning(f"Failed/No data: {', '.join(results['failed'])}")
    
    if not all_papers:
        logger.warning("No papers found!")
        if args.compact:
            print("📡 今日暂无相关论文")
        return
    
    # Generate report
    report_path = generate_report(all_papers, args.output_dir)
    
    if args.compact:
        summary = generate_compact_summary(all_papers, args.max_compact)
        print(summary)


if __name__ == '__main__':
    main()
