#!/usr/bin/env python3
"""
Citation Maven™ 2.0 - Patent Pending
Academic Citation Processing System
- URLs are ALWAYS clickable, regardless of citation style setting
- Interview and oral history citation support
- Dynamic page references with PAGEREF fields
- 9 academic citation styles
"""

import os
import re
import shutil
import zipfile
import uuid
import secrets
import logging
import traceback
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timedelta
import atexit

from flask import Flask, render_template, request, send_file, flash, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

# --- Configuration ---
@dataclass
class Config:
    SECRET_KEY: str = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    MAX_CONTENT_LENGTH: int = int(os.environ.get('MAX_CONTENT_LENGTH', 100 * 1024 * 1024))
    UPLOAD_FOLDER: str = os.path.join(tempfile.gettempdir() if os.environ.get('RAILWAY_ENVIRONMENT') else os.getcwd(), 'temp_uploads')
    ALLOWED_EXTENSIONS: Set[str] = field(default_factory=lambda: {'docx'})
    XML_NAMESPACES: Dict[str, str] = field(default_factory=lambda: {
        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
        'xml': 'http://www.w3.org/XML/1998/namespace',
        'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
        'rels': 'http://schemas.openxmlformats.org/package/2006/relationships'
    })
    FLASK_ENV: str = os.environ.get('FLASK_ENV', 'production')

config = Config()
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Helpers ---
def qn(tag: str) -> str:
    """Get qualified name for XML tags."""
    if ':' in tag:
        prefix, tag_name = tag.split(':', 1)
        uri = config.XML_NAMESPACES.get(prefix)
        if uri:
            return f"{{{uri}}}{tag_name}"
    return tag

def register_namespaces():
    for prefix, uri in config.XML_NAMESPACES.items():
        ET.register_namespace(prefix, uri)

register_namespaces()

def cleanup_old_files():
    """Clean up old temporary files."""
    try:
        cutoff = datetime.now() - timedelta(hours=1)
        p = Path(config.UPLOAD_FOLDER)
        if p.exists():
            for f in p.iterdir():
                if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    try:
                        f.unlink()
                    except:
                        pass
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")

atexit.register(cleanup_old_files)

# --- Utility function to extract URLs from text ---
def extract_url_from_text(text: str) -> Tuple[str, Optional[str]]:
    """
    Extract URL from text and return (text_without_url, url).
    This is used when citation formatting is OFF but we still need clickable URLs.
    """
    # Look for URLs with or without "Accessed" prefix
    url_pattern = r'(?:Accessed|accessed|Retrieved|retrieved)?\s*(?:on\s+)?(?:[A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})?\s*[\s,.]*([Hh]ttps?://[^\s]+)'
    url_match = re.search(url_pattern, text)
    
    if url_match:
        url = url_match.group(1)
        # Keep the text before URL as-is
        text_before_url = text[:url_match.start(1)].rstrip()
        # Check if there's text after the URL
        text_after_url = text[url_match.end(1):].strip()
        
        if text_after_url:
            return f"{text_before_url} {text_after_url}", url
        else:
            return text_before_url, url
    
    # Try simpler URL pattern
    simple_url = re.search(r'[Hh]ttps?://[^\s]+', text)
    if simple_url:
        url = simple_url.group(0)
        text_without = text.replace(url, '').strip()
        return text_without, url
    
    return text, None

# --- Data Models ---
@dataclass
class CitationData:
    """Citation components."""
    raw: str
    type: str = 'generic'
    author: Optional[str] = None
    title: Optional[str] = None
    city: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[str] = None
    pub_raw: Optional[str] = None
    page: Optional[str] = None
    journal: Optional[str] = None
    details: Optional[str] = None
    url: Optional[str] = None
    access_date: Optional[str] = None
    url_suffix: Optional[str] = None
    fingerprint: Optional[str] = None
    # Interview fields
    interviewee: Optional[str] = None
    interviewer: Optional[str] = None
    interview_date: Optional[str] = None
    interview_location: Optional[str] = None

# --- Citation Engine (same as v7.9 with interview support) ---
class CitationEngine:
    """Citation parser and formatter with interview support."""
    
    MED_JOURNALS = [
        'Am J Psychiatry', 'American Journal of Psychiatry', 'JAMA', 'NEJM', 
        'Lancet', 'BMJ', 'Arch Gen Psychiatry', 'Archives of General Psychiatry',
        'Ann Intern Med', 'N Engl J Med', 'Annals of Internal Medicine'
    ]

    def __init__(self, style: str = 'chicago'):
        self.style = style.lower() if style else 'chicago'
        self.seen_works = {}
        self.history = []

    @staticmethod
    def generate_fingerprint(author: Optional[str], title: Optional[str]) -> Optional[str]:
        if not title and not author: 
            return None
        auth_str = re.sub(r'\W+', '', author).lower() if author else "no_auth"
        title_str = re.sub(r'\W+', '', title).lower()[:25] if title else "no_title"
        return f"{auth_str}_{title_str}"

    @staticmethod
    def clean_text(text: str) -> str:
        text = re.sub(r'(?<=[\s(,])p{1,2}\.\s*(?=\d)', '', text)
        text = re.sub(r'(\d)-(\d)', r'\1–\2', text)
        text = re.sub(r'[\u2018\u2019]', "'", text)
        text = re.sub(r'[\u201c\u201d]', '"', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def fix_author_name(author_str: str) -> str:
        """Fix author name formatting - handle middle names correctly."""
        if not author_str:
            return author_str
        
        if ' and ' in author_str or ' & ' in author_str:
            separator = ' and ' if ' and ' in author_str else ' & '
            authors = author_str.split(separator)
            fixed_authors = [CitationEngine.fix_single_author(auth.strip()) for auth in authors]
            return separator.join(fixed_authors)
        
        return CitationEngine.fix_single_author(author_str)
    
    @staticmethod
    def fix_single_author(author: str) -> str:
        """Fix single author - only flip if comma present."""
        author = author.strip()
        
        if 'et al' in author.lower():
            return author
        
        # Only flip if there's a comma (Last, First format)
        if ',' in author:
            parts = author.split(',', 1)
            if len(parts) == 2:
                last_name = parts[0].strip()
                first_middle = parts[1].strip()
                return f"{first_middle} {last_name}"
        
        return author

    def parse(self, text: str) -> CitationData:
        """Parse citation extracting all components including URLs and interviews."""
        data = CitationData(raw=text)
        
        try:
            # Extract URL and access date first
            url_pattern = r'(?:Accessed|accessed|Retrieved|retrieved)\s+(?:on\s+)?([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})[\s,.]*([Hh]ttps?://[^\s]+)'
            url_match = re.search(url_pattern, text)
            
            if url_match:
                data.access_date = url_match.group(1)
                data.url = url_match.group(2)
                data.url_suffix = f"Accessed {data.access_date}"
                text = text[:url_match.start()].strip().rstrip('.,')
            else:
                url_only = re.search(r'[Hh]ttps?://[^\s]+', text)
                if url_only:
                    data.url = url_only.group(0)
                    data.url_suffix = ""
                    text = text[:url_only.start()].strip().rstrip('.,')
            
            text = self.clean_text(text)
            
            # Extract page numbers
            page_match = re.search(r'[,.]\s*(\d+[-\u2013]?\d*)\.?$', text)
            if page_match:
                data.page = page_match.group(1)
                text = text[:page_match.start()].strip().rstrip('.,')
            
            # Check for interview FIRST before other parsing
            try:
                if self._parse_interview(text, data): return data
            except Exception as e:
                logger.warning(f"Interview parsing failed: {e}, falling back to generic")
            
            if self._parse_archival(text, data): return data
            if self._parse_legal(text, data): return data
            if self._parse_medical(text, data): return data
            if self._parse_book(text, data): return data
            
            self._parse_generic(text, data)
            
        except Exception as e:
            logger.error(f"Citation parsing error: {e}, returning raw")
            data.title = text
            
        return data

    def _parse_interview(self, text: str, data: CitationData) -> bool:
        """Parse interview/oral history citations."""
        # Pattern 1: "interview by author" at the beginning
        pattern1 = r'^[Ii]nterview\s+(?:by|with)\s+(?:the\s+)?author[,.]?\s*(.*)'
        match1 = re.match(pattern1, text)
        if match1:
            data.type = 'interview'
            data.interviewer = 'author'
            rest = match1.group(1).strip()
            self._extract_interview_details(rest, data)
            return True
        
        # Pattern 2: Name followed by "interview by author"
        pattern2 = r'^([^,]+),\s*[Ii]nterview\s+(?:by|with)\s+(?:the\s+)?author[,.]?\s*(.*)'
        match2 = re.match(pattern2, text)
        if match2:
            data.type = 'interview'
            data.interviewee = match2.group(1).strip()
            data.interviewer = 'author'
            rest = match2.group(2).strip()
            self._extract_interview_details(rest, data)
            return True
        
        # Pattern 3: "oral history" or general interview mention
        if 'oral history' in text.lower() or 'interview' in text.lower():
            data.type = 'interview'
            parts = text.split(',', 1)
            if len(parts) > 1 and 'interview' not in parts[0].lower():
                data.interviewee = self.fix_author_name(parts[0].strip())
                rest = parts[1].strip()
                self._extract_interview_details(rest, data)
            else:
                data.title = text
            return True
        
        return False
    
    def _extract_interview_details(self, text: str, data: CitationData):
        """Extract date, location, and other details from interview text."""
        date_pattern = r'([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})'
        date_match = re.search(date_pattern, text)
        if date_match:
            data.interview_date = date_match.group(1)
            before_date = text[:date_match.start()].strip().rstrip(',')
            after_date = text[date_match.end():].strip().lstrip(',').strip()
            
            if before_date and not any(skip in before_date.lower() for skip in ['interview', 'by', 'with']):
                data.interview_location = before_date
            
            if after_date:
                data.details = after_date
        else:
            data.details = text

    def _parse_book(self, text: str, data: CitationData) -> bool:
        pub_match = re.search(r'\(?([A-Za-z\s\.]+:\s*[^,()]+,\s*(\d{4}))\)?', text)
        if pub_match:
            data.type = 'book'
            data.pub_raw = pub_match.group(1)
            data.year = pub_match.group(2)
            
            pub_block = data.pub_raw.replace(f", {data.year}", "")
            if ':' in pub_block:
                try:
                    data.city, data.publisher = [x.strip() for x in pub_block.split(':', 1)]
                except:
                    data.publisher = pub_block
            else:
                data.publisher = pub_block

            pre_pub = text[:pub_match.start()].strip().rstrip('.,')
            parts = re.split(r'\.\s+(?=[A-Z"\'\u201c])', pre_pub, 1)
            
            if len(parts) > 1:
                raw_auth = parts[0].strip()
                data.author = self.fix_author_name(raw_auth)
                data.title = parts[1].strip()
            else:
                data.title = pre_pub
            return True
        return False

    def _parse_medical(self, text: str, data: CitationData) -> bool:
        for journal in self.MED_JOURNALS:
            if journal in text:
                try:
                    pre_j, post_j = text.split(journal, 1)
                    parts = re.split(r'\.\s+(?=[A-Z"\'\u201c])', pre_j.strip(), 1)
                    
                    if len(parts) > 0:
                        raw_auth = parts[0].strip()
                        data.author = self.fix_author_name(raw_auth)
                        data.author = re.sub(r'\bet\s+al\.?', 'et al.', data.author, flags=re.IGNORECASE)
                    
                    data.title = parts[1].strip(' .') if len(parts) > 1 else "Unknown"
                    data.journal = journal
                    data.details = post_j.strip()
                    data.type = 'medical'
                    return True
                except:
                    continue
        return False

    def _parse_archival(self, text: str, data: CitationData) -> bool:
        if "Box" in text or "Folder" in text or "Archive" in text or "Collection" in text:
            data.type = 'archival'
            data.title = text
            return True
        return False
    
    def _parse_legal(self, text: str, data: CitationData) -> bool:
        if re.search(r'\s+v\.\s+', text):
            data.type = 'legal'
            data.title = text
            return True
        return False

    def _parse_generic(self, text: str, data: CitationData):
        """Generic parsing - be more careful about author detection."""
        if 'interview' in text.lower() or 'oral history' in text.lower():
            data.title = text
            return
        
        parts = re.split(r'\.\s+(?=[A-Z"\'\u201c])', text, 1)
        if len(parts) > 1:
            first_part = parts[0].strip()
            if len(first_part) < 60 and not any(word in first_part.lower() for word in ['the', 'a', 'an', 'this', 'that']):
                data.author = self.fix_author_name(first_part)
                data.title = parts[1]
            else:
                data.title = text
        else:
            data.title = text

    def format(self, raw_text: str) -> Tuple[str, Optional[str]]:
        """Format citation and return (formatted_text, url) separately."""
        parsed = self.parse(raw_text)
        
        if not parsed.title and not parsed.author and not parsed.interviewee:
            base = self.clean_text(raw_text)
            if parsed.url_suffix and parsed.url:
                return f"{base}. {parsed.url_suffix}.", parsed.url
            elif parsed.url:
                return base, parsed.url
            return base, None

        # Special handling for interviews
        if parsed.type == 'interview':
            formatted = self._format_interview(parsed)
            if parsed.url_suffix and parsed.url:
                return f"{formatted}. {parsed.url_suffix}.", parsed.url
            elif parsed.url:
                return formatted, parsed.url
            return formatted, None

        fingerprint = self.generate_fingerprint(parsed.author, parsed.title)
        
        # Check for Ibid or short form
        if self.history and self.history[-1].fingerprint == fingerprint:
            result = self._format_ibid(parsed)
        elif fingerprint and fingerprint in self.seen_works:
            result = self._format_short(parsed, self.seen_works[fingerprint])
        else:
            if fingerprint:
                self.seen_works[fingerprint] = parsed
            result = self._format_full(parsed)
        
        self.history.append(parsed)
        
        # Return formatted text and URL separately
        if parsed.url_suffix and parsed.url:
            return f"{result}. {parsed.url_suffix}.", parsed.url
        elif parsed.url:
            return result, parsed.url
        
        return result, None

    def _format_interview(self, d: CitationData) -> str:
        """Format interview citations properly."""
        if self.style in ['chicago', 'turabian']:
            parts = []
            if d.interviewee:
                parts.append(d.interviewee)
            parts.append(f"interview by {d.interviewer if d.interviewer else 'author'}")
            if d.interview_location:
                parts.append(d.interview_location)
            if d.interview_date:
                parts.append(d.interview_date)
            elif d.details and any(month in d.details for month in ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']):
                parts.append(d.details)
                d.details = None
            if d.details:
                parts.append(d.details)
            return ', '.join(parts)
        else:
            if d.interviewee:
                return f"{d.interviewee}, interview, {d.interview_date if d.interview_date else d.details if d.details else ''}"
            elif d.title:
                return d.title
            else:
                return self.clean_text(d.raw)

    def _format_ibid(self, data: CitationData) -> str:
        if self.style in ['ama', 'vancouver']:
            return "Ibid."
        pg = f", {data.page}" if data.page else ""
        if self.style in ['oxford', 'mhra']:
            pg = f", p. {data.page}" if data.page else ""
        return f"Ibid.{pg}"

    def _format_short(self, curr: CitationData, prev: CitationData) -> str:
        if prev.type == 'interview' and prev.interviewee:
            return f"{prev.interviewee}, interview{f', {curr.page}' if curr.page else ''}"
        
        short_title = self.get_short_title(prev.title)
        auth = curr.author if curr.author else prev.author
        pg = f", {curr.page}" if curr.page else ""
        
        if self.style in ['oxford', 'mhra']:
            pg = f", p. {curr.page}" if curr.page else ""
            return f"{auth}, {short_title}{pg}" if auth else f"{short_title}{pg}"
        elif self.style == 'bluebook':
            return f"{auth}, supra{pg}." if auth else f"{short_title}, supra{pg}."
        
        return f"{auth}, {short_title}{pg}" if auth else f"{short_title}{pg}"

    def _format_full(self, d: CitationData) -> str:
        auth_str = f"{d.author}, " if d.author else ""
        
        if self.style in ['chicago', 'turabian']:
            if d.type == 'book' and d.pub_raw:
                return f"{auth_str}{d.title} ({d.pub_raw}){f', {d.page}' if d.page else ''}"
            elif d.type == 'medical':
                return f"{auth_str}{d.title} {d.journal} {d.details}{f', {d.page}' if d.page else ''}"
            else:
                return f"{auth_str}{d.title}{f', {d.page}' if d.page else ''}"
        
        elif self.style == 'bluebook':
            if d.type == 'legal':
                return f"{d.title}{f', {d.page}' if d.page else ''}"
            return f"{auth_str}{d.title} {d.page if d.page else ''} ({d.year if d.year else ''})"
        
        elif self.style == 'ama':
            parts = []
            if d.author: parts.append(d.author)
            if d.title: parts.append(d.title)
            if d.journal: parts.append(d.journal)
            elif d.publisher: parts.append(d.publisher)
            if d.year and d.details: parts.append(f"{d.year};{d.details}")
            elif d.year: parts.append(d.year)
            if d.page: parts.append(d.page)
            return ". ".join(parts) + "."
        
        elif self.style in ['oxford', 'mhra']:
            pg_str = f", p. {d.page}" if d.page else ""
            if d.type == 'book' and d.pub_raw:
                return f"{auth_str}{d.title} ({d.pub_raw}){pg_str}"
            return f"{auth_str}{d.title}{pg_str}"
        
        elif self.style == 'oscola':
            pub_block = f"({d.publisher} {d.year})" if (d.publisher and d.year) else ""
            return f"{auth_str}{d.title} {pub_block} {d.page if d.page else ''}"
        
        elif self.style == 'vancouver':
            parts = []
            if d.author: parts.append(d.author)
            if d.title: parts.append(d.title)
            if d.publisher: parts.append(d.publisher)
            if d.year: parts.append(d.year)
            if d.page: parts.append(d.page)
            return ". ".join(parts) + "."
        
        return self.clean_text(d.raw)

    @staticmethod
    def get_short_title(full_title: str) -> str:
        if not full_title: return ""
        short = full_title.split(':')[0] if ':' in full_title else full_title
        short = re.sub(r'^(The|A|An)\s+', '', short)
        words = short.split()
        return ' '.join(words[:5]) if len(words) > 5 else short

# --- Incipit Extractor (same as before) ---
class IncipitExtractor:
    """Extract incipits with epigraph support."""
    
    def __init__(self, word_count: int = 3):
        self.word_count = word_count
    
    def extract_from_tree(self, doc_tree: ET.Element) -> Dict[str, str]:
        contexts = {}
        
        for p in doc_tree.iter(qn('w:p')):
            is_epigraph = self._is_epigraph_paragraph(p)
            p_text = ""
            ref_indices = []
            
            for child in p.iter():
                if child.tag == qn('w:t') and child.text:
                    p_text += child.text
                elif child.tag == qn('w:endnoteReference'):
                    e_id = child.get(qn('w:id'))
                    if e_id:
                        ref_indices.append((e_id, len(p_text), is_epigraph))
            
            for e_id, idx, is_epigraph in ref_indices:
                if is_epigraph:
                    contexts[e_id] = self._extract_epigraph_incipit(p_text)
                else:
                    contexts[e_id] = self._extract_regular_incipit(p_text, idx)
        
        return contexts
    
    def _is_epigraph_paragraph(self, para: ET.Element) -> bool:
        pPr = para.find(qn('w:pPr'))
        if pPr is not None:
            pStyle = pPr.find(qn('w:pStyle'))
            if pStyle is not None:
                style_val = pStyle.get(qn('w:val'), '').lower()
                epigraph_styles = ['epigraph', 'quote', 'blockquote', 'block', 'extract', 'verse']
                if any(s in style_val for s in epigraph_styles):
                    return True
            
            ind = pPr.find(qn('w:ind'))
            if ind is not None:
                if ind.get(qn('w:left')) or ind.get(qn('w:right')):
                    return True
        
        all_italic = True
        run_count = 0
        for r in para.findall('.//' + qn('w:r')):
            run_count += 1
            rPr = r.find(qn('w:rPr'))
            if rPr is None or rPr.find(qn('w:i')) is None:
                all_italic = False
                break
        
        return all_italic and run_count > 0
    
    def _extract_epigraph_incipit(self, text: str) -> str:
        clean_text = text.strip()
        clean_text = re.sub(r'^["\'\u201c\u2018]+', '', clean_text)
        words = clean_text.split()
        
        if len(words) >= self.word_count:
            selected_words = words[:self.word_count]
        else:
            selected_words = words
        
        if selected_words:
            last_word = selected_words[-1]
            last_word = re.sub(r'["\'\u201d\u2019,;:!?]+$', '', last_word)
            selected_words[-1] = last_word
        
        return ' '.join(selected_words)
    
    def _extract_regular_incipit(self, text: str, pos: int) -> str:
        text_before = text[:pos]
        if not text_before:
            return ""
        
        pattern = r'(?<!Dr)(?<!Mr)(?<!Ms)(?<!Mrs)(?<!Prof)(?<!Rev)(?<=[.!?])\s+(?=[A-Z])'
        sentences = re.split(pattern, text_before)
        
        if not sentences:
            return ""
        
        current_sentence = sentences[-1].strip()
        current_sentence = re.sub(r'^["\'\u201c\u2018\s]+', '', current_sentence)
        
        words = current_sentence.split()
        if len(words) > self.word_count:
            selected_words = words[:self.word_count]
        else:
            selected_words = words
        
        if selected_words:
            selected_words[-1] = re.sub(r'[.,;:!?"\'\u201d\u2019]+$', '', selected_words[-1])
        
        return ' '.join(selected_words)

# --- Document Processor with URL fix ---
class DocumentProcessor:
    """Process Word documents with configurable options and ALWAYS clickable URLs."""
    
    def __init__(self, input_path: Path, output_path: Path, options: Dict):
        self.input_path = input_path
        self.output_path = output_path
        self.options = options
        self.temp_dir = Path(config.UPLOAD_FOLDER) / f"proc_{uuid.uuid4().hex}"
        self.hyperlink_counter = 1000
        self.bookmark_counter = 1
        
        if options.get('apply_cms'):
            style = options.get('citation_style', 'chicago')
            self.cit_engine = CitationEngine(style=style)
        else:
            self.cit_engine = None
    
    def run(self) -> Tuple[bool, str]:
        """Process document with all options."""
        os.makedirs(self.temp_dir, exist_ok=True)
        try:
            self._extract_docx()
            
            doc_tree = ET.parse(str(self.temp_dir / 'word' / 'document.xml'))
            endnotes_path = self.temp_dir / 'word' / 'endnotes.xml'
            
            if not endnotes_path.exists():
                return False, "No endnotes found in document."
            
            endnotes_tree = ET.parse(str(endnotes_path))
            
            extractor = IncipitExtractor(self.options.get('word_count', 3))
            contexts = extractor.extract_from_tree(doc_tree.getroot())
            
            if self.options.get('keep_superscripts', False):
                bookmarks = self._add_bookmarks_keep_superscripts(doc_tree.getroot())
            else:
                bookmarks = self._replace_references_with_bookmarks(doc_tree.getroot())
            
            count, hyperlinks = self._create_notes_section_with_formatting(
                doc_tree.getroot(), endnotes_tree.getroot(), contexts, bookmarks
            )
            
            if hyperlinks:
                self._add_hyperlink_relationships(hyperlinks)
            
            doc_tree.write(str(self.temp_dir / 'word' / 'document.xml'), 
                          encoding='UTF-8', xml_declaration=True)
            
            self._repack_docx()
            
            style_msg = f" ({self.options.get('citation_style', 'chicago')} style)" if self.cit_engine else ""
            return True, f"Successfully processed {count} endnotes{style_msg}"
            
        except Exception as e:
            logger.error(f"Processing failed: {traceback.format_exc()}")
            return False, str(e)
        finally:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _extract_docx(self):
        with zipfile.ZipFile(self.input_path, 'r') as z:
            z.extractall(self.temp_dir)
    
    def _repack_docx(self):
        with zipfile.ZipFile(self.output_path, 'w', zipfile.ZIP_DEFLATED) as z:
            for file_path in self.temp_dir.rglob('*'):
                if file_path.is_file():
                    z.write(file_path, file_path.relative_to(self.temp_dir))
    
    def _add_bookmarks_keep_superscripts(self, doc_root: ET.Element) -> Dict[str, str]:
        parent_map = {c: p for p in doc_root.iter() for c in p}
        bookmarks = {}
        
        for ref in doc_root.findall('.//' + qn('w:endnoteReference')):
            note_id = ref.get(qn('w:id'))
            if note_id:
                bookmark_name = f"_Ref_Note_{note_id}"
                bookmarks[note_id] = bookmark_name
                
                parent = parent_map.get(ref)
                if parent is not None and parent.tag == qn('w:r'):
                    para = parent_map.get(parent)
                    if para is not None:
                        run_index = list(para).index(parent)
                        
                        bookmark_start = ET.Element(qn('w:bookmarkStart'))
                        bookmark_start.set(qn('w:id'), str(self.bookmark_counter))
                        bookmark_start.set(qn('w:name'), bookmark_name)
                        para.insert(run_index, bookmark_start)
                        
                        bookmark_end = ET.Element(qn('w:bookmarkEnd'))
                        bookmark_end.set(qn('w:id'), str(self.bookmark_counter))
                        para.insert(run_index + 2, bookmark_end)
                        
                        self.bookmark_counter += 1
        
        return bookmarks
    
    def _replace_references_with_bookmarks(self, doc_root: ET.Element) -> Dict[str, str]:
        parent_map = {c: p for p in doc_root.iter() for c in p}
        bookmarks = {}
        
        for ref in doc_root.findall('.//' + qn('w:endnoteReference')):
            note_id = ref.get(qn('w:id'))
            if note_id:
                bookmark_name = f"_Ref_Note_{note_id}"
                bookmarks[note_id] = bookmark_name
                
                parent = parent_map.get(ref)
                if parent is not None and parent.tag == qn('w:r'):
                    para = parent_map.get(parent)
                    if para is not None:
                        run_index = list(para).index(parent)
                        
                        bookmark_start = ET.Element(qn('w:bookmarkStart'))
                        bookmark_start.set(qn('w:id'), str(self.bookmark_counter))
                        bookmark_start.set(qn('w:name'), bookmark_name)
                        para.insert(run_index, bookmark_start)
                        
                        bookmark_end = ET.Element(qn('w:bookmarkEnd'))
                        bookmark_end.set(qn('w:id'), str(self.bookmark_counter))
                        para.insert(run_index + 1, bookmark_end)
                        
                        self.bookmark_counter += 1
                        para.remove(parent)
        
        return bookmarks
    
    def _create_notes_section_with_formatting(self, doc_root: ET.Element, endnotes_root: ET.Element, 
                                               contexts: Dict[str, str], bookmarks: Dict[str, str]) -> Tuple[int, List[Tuple[str, str]]]:
        """
        Create Notes section with proper formatting and ALWAYS clickable URLs.
        BUG FIX: When superscripts are removed (keep_superscripts=False), 
        page numbers appear in italics with two spaces, not in parentheses.
        """
        notes_data = []
        hyperlinks = []
        
        for note in endnotes_root.iter(qn('w:endnote')):
            note_id = note.get(qn('w:id'))
            
            if note_id and note_id not in ['-1', '0']:
                text_parts = []
                url_parts = []
                
                for p in note.findall('.//' + qn('w:p')):
                    for element in p:
                        if element.tag == qn('w:r'):
                            for t in element.findall('.//' + qn('w:t')):
                                if t.text:
                                    text_parts.append(t.text)
                        elif element.tag == qn('w:hyperlink'):
                            for t in element.findall('.//' + qn('w:t')):
                                if t.text:
                                    url_parts.append(t.text)
                
                full_text = ''.join(text_parts).strip()
                if url_parts:
                    url_text = ' '.join(url_parts)
                    if url_text not in full_text:
                        full_text += f" {url_text}"
                
                if not full_text:
                    continue
                
                # CRITICAL FIX: Extract URLs even when citation formatting is OFF
                if self.cit_engine:
                    # Use citation engine for formatting
                    formatted, url = self.cit_engine.format(full_text)
                else:
                    # NO citation formatting, but still extract URLs
                    formatted, url = extract_url_from_text(full_text)
                    # Keep original formatting but make URLs clickable
                
                incipit = contexts.get(note_id, "")
                bookmark = bookmarks.get(note_id)
                
                notes_data.append((note_id, incipit, formatted, url, bookmark))
        
        if not notes_data:
            return 0, []
        
        body = doc_root.find(qn('w:body'))
        if body is None:
            return 0, []
        
        break_para = ET.SubElement(body, qn('w:p'))
        break_run = ET.SubElement(break_para, qn('w:r'))
        ET.SubElement(break_run, qn('w:br'), {qn('w:type'): 'page'})
        
        heading_para = ET.SubElement(body, qn('w:p'))
        heading_pPr = ET.SubElement(heading_para, qn('w:pPr'))
        heading_style = ET.SubElement(heading_pPr, qn('w:pStyle'))
        heading_style.set(qn('w:val'), 'Heading1')
        heading_run = ET.SubElement(heading_para, qn('w:r'))
        heading_rPr = ET.SubElement(heading_run, qn('w:rPr'))
        ET.SubElement(heading_rPr, qn('w:b'))
        ET.SubElement(heading_rPr, qn('w:sz'), {qn('w:val'): '32'})
        heading_text = ET.SubElement(heading_run, qn('w:t'))
        heading_text.text = "Notes"
        
        for note_id, incipit, formatted_text, url, bookmark in notes_data:
            note_para = ET.SubElement(body, qn('w:p'))
            
            note_pPr = ET.SubElement(note_para, qn('w:pPr'))
            spacing = ET.SubElement(note_pPr, qn('w:spacing'))
            spacing.set(qn('w:after'), '120')
            
            # Check if we're keeping superscripts or not
            if self.options.get('keep_superscripts', False):
                # SUPERSCRIPTS KEPT: Include note number and parenthetical page reference
                num_run = ET.SubElement(note_para, qn('w:r'))
                num_text = ET.SubElement(num_run, qn('w:t'))
                num_text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                num_text.text = f"{note_id}. "
                
                if bookmark:
                    # Add parenthetical page reference
                    paren_run1 = ET.SubElement(note_para, qn('w:r'))
                    paren_text1 = ET.SubElement(paren_run1, qn('w:t'))
                    paren_text1.text = "(p. "
                    
                    fld_simple = ET.SubElement(note_para, qn('w:fldSimple'))
                    fld_simple.set(qn('w:instr'), f" PAGEREF {bookmark} \\h ")
                    
                    fld_run = ET.SubElement(fld_simple, qn('w:r'))
                    fld_text = ET.SubElement(fld_run, qn('w:t'))
                    fld_text.text = "0"
                    
                    paren_run2 = ET.SubElement(note_para, qn('w:r'))
                    paren_text2 = ET.SubElement(paren_run2, qn('w:t'))
                    paren_text2.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                    paren_text2.text = ") "
            else:
                # SUPERSCRIPTS REMOVED: NO note number, just italic page number
                if bookmark:
                    # Add italic page number directly (no note number)
                    fld_simple = ET.SubElement(note_para, qn('w:fldSimple'))
                    fld_simple.set(qn('w:instr'), f" PAGEREF {bookmark} \\h ")
                    
                    fld_run = ET.SubElement(fld_simple, qn('w:r'))
                    fld_rPr = ET.SubElement(fld_run, qn('w:rPr'))
                    ET.SubElement(fld_rPr, qn('w:i'))  # Make page number italic
                    fld_text = ET.SubElement(fld_run, qn('w:t'))
                    fld_text.text = "0"  # Will be updated by Word
                    
                    # Add two spaces after page number
                    space_run = ET.SubElement(note_para, qn('w:r'))
                    space_text = ET.SubElement(space_run, qn('w:t'))
                    space_text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                    space_text.text = "  "  # Two spaces
            
            if incipit:
                incipit_run = ET.SubElement(note_para, qn('w:r'))
                incipit_rPr = ET.SubElement(incipit_run, qn('w:rPr'))
                
                if self.options.get('format_style') == 'italic':
                    ET.SubElement(incipit_rPr, qn('w:i'))
                else:
                    ET.SubElement(incipit_rPr, qn('w:b'))
                
                incipit_text = ET.SubElement(incipit_run, qn('w:t'))
                incipit_text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                incipit_text.text = f"{incipit}: "
            
            # Add citation text
            text_run = ET.SubElement(note_para, qn('w:r'))
            text_t = ET.SubElement(text_run, qn('w:t'))
            text_t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            
            # CRITICAL: Always create hyperlink if URL exists, regardless of citation formatting
            if url:
                # Add text before URL
                text_t.text = formatted_text.rstrip() + " "
                
                # Create hyperlink element
                r_id = f"rIdLink{self.hyperlink_counter}"
                self.hyperlink_counter += 1
                hyperlinks.append((r_id, url))
                
                hyperlink = ET.SubElement(note_para, qn('w:hyperlink'), {qn('r:id'): r_id})
                
                # Add hyperlink text run with blue underline style
                link_run = ET.SubElement(hyperlink, qn('w:r'))
                link_rPr = ET.SubElement(link_run, qn('w:rPr'))
                ET.SubElement(link_rPr, qn('w:rStyle'), {qn('w:val'): 'Hyperlink'})
                link_text = ET.SubElement(link_run, qn('w:t'))
                link_text.text = url
            else:
                # No URL, just add the formatted text
                text_t.text = formatted_text
        
        return len(notes_data), hyperlinks
    
    def _add_hyperlink_relationships(self, hyperlinks: List[Tuple[str, str]]):
        rels_path = self.temp_dir / 'word' / '_rels' / 'document.xml.rels'
        
        if rels_path.exists():
            tree = ET.parse(str(rels_path))
            root = tree.getroot()
        else:
            root = ET.Element(qn('rels:Relationships'))
            tree = ET.ElementTree(root)
        
        for r_id, url in hyperlinks:
            rel = ET.SubElement(root, qn('rels:Relationship'))
            rel.set('Id', r_id)
            rel.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink')
            rel.set('Target', url)
            rel.set('TargetMode', 'External')
        
        tree.write(str(rels_path), encoding='UTF-8', xml_declaration=True)
    
    def preview_changes(self) -> List[Dict]:
        preview = []
        try:
            self._extract_docx()
            endnotes_path = self.temp_dir / 'word' / 'endnotes.xml'
            
            if not endnotes_path.exists():
                return []
            
            endnotes_tree = ET.parse(str(endnotes_path))
            doc_tree = ET.parse(str(self.temp_dir / 'word' / 'document.xml'))
            
            extractor = IncipitExtractor(self.options.get('word_count', 3))
            contexts = extractor.extract_from_tree(doc_tree.getroot())
            
            for note in endnotes_tree.getroot().iter(qn('w:endnote')):
                note_id = note.get(qn('w:id'))
                if note_id and note_id not in ['-1', '0']:
                    text_runs = []
                    for t in note.findall('.//' + qn('w:t')):
                        if t.text:
                            text_runs.append(t.text)
                    
                    original_text = ''.join(text_runs).strip()
                    if original_text:
                        incipit = contexts.get(note_id, "")
                        
                        if self.cit_engine:
                            formatted, url = self.cit_engine.format(original_text)
                            if url:
                                formatted = f"{formatted} {url}"
                            parsed = self.cit_engine.parse(original_text)
                            note_type = parsed.type
                        else:
                            # Still extract URL even without formatting
                            formatted, url = extract_url_from_text(original_text)
                            if url:
                                formatted = f"{formatted} {url}"
                            note_type = 'generic'
                        
                        final_formatted = f"{incipit}: {formatted}" if incipit else formatted
                        
                        preview.append({
                            'raw': original_text,
                            'processed': final_formatted,
                            'type': note_type
                        })
            
            return preview[:5]
            
        except Exception as e:
            logger.error(f"Preview failed: {traceback.format_exc()}")
            return []
        finally:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)

# === Flask Application ===
app = Flask(__name__)
app.config.from_object(config)

if config.FLASK_ENV == 'production':
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/preview', methods=['POST'])
def preview():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    fname = secure_filename(file.filename) if file.filename else 'document.docx'
    temp_path = Path(config.UPLOAD_FOLDER) / f"preview_{uuid.uuid4().hex}_{fname}"
    
    try:
        file.save(temp_path)
        
        options = {
            'word_count': int(request.form.get('word_count', 3)),
            'format_style': request.form.get('format_style', 'bold'),
            'apply_cms': request.form.get('apply_cms', 'yes') == 'yes',
            'citation_style': request.form.get('citation_style', 'chicago'),
            'keep_superscripts': request.form.get('keep_superscripts', 'no') == 'yes'
        }
        
        proc = DocumentProcessor(temp_path, temp_path, options)
        preview_data = proc.preview_changes()
        
        return jsonify(preview_data)
        
    except Exception as e:
        logger.error(f"Preview error: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500
    finally:
        if temp_path.exists():
            try:
                os.remove(temp_path)
            except:
                pass

@app.route('/convert', methods=['POST'])
def convert():
    if 'file' not in request.files:
        flash('No file provided', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    if not file.filename or not file.filename.endswith('.docx'):
        flash('Please upload a Word document (.docx)', 'error')
        return redirect(url_for('index'))
    
    fname = secure_filename(file.filename)
    uid = uuid.uuid4().hex[:8]
    input_path = Path(config.UPLOAD_FOLDER) / f"{uid}_{fname}"
    output_path = Path(config.UPLOAD_FOLDER) / f"CitationMaven_{uid}_{Path(fname).stem}.docx"
    
    try:
        file.save(input_path)
        
        options = {
            'word_count': int(request.form.get('word_count', 3)),
            'format_style': request.form.get('format_style', 'bold'),
            'apply_cms': request.form.get('apply_cms', 'yes') == 'yes',
            'citation_style': request.form.get('citation_style', 'chicago'),
            'keep_superscripts': request.form.get('keep_superscripts', 'no') == 'yes'
        }
        
        proc = DocumentProcessor(input_path, output_path, options)
        success, msg = proc.run()
        
        if success:
            return send_file(
                output_path,
                as_attachment=True,
                download_name=f"CitationMaven_{Path(fname).stem}.docx",
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
        else:
            flash(f"Processing failed: {msg}", 'error')
            return redirect(url_for('index'))
            
    except Exception as e:
        logger.error(f"Conversion failed: {traceback.format_exc()}")
        flash(f"Error: {str(e)}", 'error')
        return redirect(url_for('index'))
    finally:
        for p in [input_path, output_path]:
            if p.exists():
                try:
                    os.remove(p)
                except:
                    pass
        cleanup_old_files()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
