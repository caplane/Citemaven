"""
Enhanced Citation Parser - Phase 1
Detects source types and intelligently parses messy citations
"""

import re
from typing import Dict, Optional, List, Tuple

class SourceType:
    """Enumeration of source types"""
    BOOK = "book"
    JOURNAL_ARTICLE = "journal_article"
    NEWSPAPER_ARTICLE = "newspaper_article"
    WEBSITE = "website"
    BOOK_CHAPTER = "book_chapter"
    UNKNOWN = "unknown"

class CitationParser:
    """Intelligent citation parser that handles multiple source types"""
    
    # Indicators for different source types
    JOURNAL_INDICATORS = [
        r'\bvol\.',
        r'\bvolume\b',
        r'\d+\s*:\s*\d+',  # Volume:Issue format
        r'\bno\.',
        r'\bissue\b',
        r'\bpp\.\s*\d+-\d+',  # Page ranges
    ]
    
    NEWSPAPER_INDICATORS = [
        r'\bNew York Times\b',
        r'\bWashington Post\b',
        r'\bWall Street Journal\b',
        r'\bGuardian\b',
        r'\bLos Angeles Times\b',
        r'\bUSA Today\b',
        r'\bChicago Tribune\b',
    ]
    
    WEBSITE_INDICATORS = [
        r'https?://',
        r'www\.',
        r'\.com',
        r'\.org',
        r'\.edu',
        r'\baccessed\b',
        r'\bretrieved\b',
    ]
    
    CHAPTER_INDICATORS = [
        r'\bin\b.*\bed\.',
        r'\bedited by\b',
        r'\bchapter\b',
    ]
    
    def __init__(self):
        self.journal_pattern = re.compile('|'.join(self.JOURNAL_INDICATORS), re.IGNORECASE)
        self.newspaper_pattern = re.compile('|'.join(self.NEWSPAPER_INDICATORS), re.IGNORECASE)
        self.website_pattern = re.compile('|'.join(self.WEBSITE_INDICATORS), re.IGNORECASE)
        self.chapter_pattern = re.compile('|'.join(self.CHAPTER_INDICATORS), re.IGNORECASE)
    
    def detect_source_type(self, text: str) -> str:
        """Detect the type of source from citation text"""
        text = text.lower()
        
        # Check for URLs/websites first (most distinct)
        if self.website_pattern.search(text):
            return SourceType.WEBSITE
        
        # Check for book chapters
        if self.chapter_pattern.search(text):
            return SourceType.BOOK_CHAPTER
        
        # Check for journal articles
        journal_matches = len(self.journal_pattern.findall(text))
        if journal_matches >= 2:  # Need multiple indicators
            return SourceType.JOURNAL_ARTICLE
        
        # Check for newspapers
        if self.newspaper_pattern.search(text):
            return SourceType.NEWSPAPER_ARTICLE
        
        # Default to book (most common academic source)
        return SourceType.BOOK
    
    def parse_citation(self, text: str) -> Dict[str, any]:
        """Parse citation text into structured data"""
        source_type = self.detect_source_type(text)
        
        # Remove leading numbers
        text = re.sub(r'^\s*\d+\s*', '', text).strip()
        
        citation_data = {
            'source_type': source_type,
            'original_text': text,
            'confidence': 'high',
            'author': None,
            'title': None,
            'year': None,
        }
        
        # Parse based on source type
        if source_type == SourceType.BOOK:
            return self._parse_book(text, citation_data)
        elif source_type == SourceType.JOURNAL_ARTICLE:
            return self._parse_journal_article(text, citation_data)
        elif source_type == SourceType.NEWSPAPER_ARTICLE:
            return self._parse_newspaper(text, citation_data)
        elif source_type == SourceType.WEBSITE:
            return self._parse_website(text, citation_data)
        elif source_type == SourceType.BOOK_CHAPTER:
            return self._parse_chapter(text, citation_data)
        
        citation_data['confidence'] = 'low'
        return citation_data
    
    def _parse_book(self, text: str, data: Dict) -> Dict:
        """Parse book citation"""
        # Extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        if year_match:
            data['year'] = year_match.group()
        
        # Extract page numbers
        page_match = re.search(r'\b(\d+(?:-\d+)?)\s*\.?\s*$', text)
        if page_match:
            data['page'] = page_match.group(1)
        
        # Try to extract author and title
        # Common patterns: "Author, Title" or "Author. Title"
        parts = re.split(r'[,.]', text, maxsplit=2)
        if len(parts) >= 2:
            potential_author = parts[0].strip()
            potential_title = parts[1].strip()
            
            # Remove quotes from title
            potential_title = re.sub(r'^["\'\u201C\u201D\u2018\u2019]+|["\'\u201C\u201D\u2018\u2019]+$', '', potential_title)
            
            if potential_author and len(potential_author) < 100:
                data['author'] = potential_author
            if potential_title and len(potential_title) > 3:
                data['title'] = potential_title
        
        data['publisher'] = None
        data['place'] = None
        
        return data
    
    def _parse_journal_article(self, text: str, data: Dict) -> Dict:
        """Parse journal article citation"""
        # Extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        if year_match:
            data['year'] = year_match.group()
        
        # Extract volume and issue
        vol_match = re.search(r'\b(?:vol\.|volume)\s*(\d+)', text, re.IGNORECASE)
        if vol_match:
            data['volume'] = vol_match.group(1)
        
        issue_match = re.search(r'\b(?:no\.|issue)\s*(\d+)', text, re.IGNORECASE)
        if issue_match:
            data['issue'] = issue_match.group(1)
        
        # Extract page range
        page_match = re.search(r'\b(\d+)\s*[-–—]\s*(\d+)', text)
        if page_match:
            data['pages'] = f"{page_match.group(1)}-{page_match.group(2)}"
        
        # Try to identify journal name (often in quotes or italics indicators)
        # Look for capitalized phrases
        journal_match = re.search(r'\b[A-Z][a-zA-Z\s]+(?:Journal|Review|Quarterly|Studies)', text)
        if journal_match:
            data['journal'] = journal_match.group()
        
        # Author is typically at the start
        parts = re.split(r'[,.]', text, maxsplit=1)
        if parts:
            data['author'] = parts[0].strip()
        
        # Article title (often in quotes)
        title_match = re.search(r'["\'\u201C\u201D\u2018\u2019]([^"\'\u201C\u201D\u2018\u2019]+)["\'\u201C\u201D\u2018\u2019]', text)
        if title_match:
            data['title'] = title_match.group(1)
        
        return data
    
    def _parse_newspaper(self, text: str, data: Dict) -> Dict:
        """Parse newspaper article citation"""
        # Extract date
        date_match = re.search(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(19|20)\d{2}\b', text, re.IGNORECASE)
        if date_match:
            data['date'] = date_match.group()
            year_match = re.search(r'(19|20)\d{2}', date_match.group())
            if year_match:
                data['year'] = year_match.group()
        
        # Extract newspaper name
        for newspaper in ['New York Times', 'Washington Post', 'Wall Street Journal', 'Guardian', 'Los Angeles Times']:
            if newspaper.lower() in text.lower():
                data['publication'] = newspaper
                break
        
        # Author at the start
        parts = re.split(r'[,.]', text, maxsplit=1)
        if parts:
            data['author'] = parts[0].strip()
        
        # Article title (in quotes)
        title_match = re.search(r'["\'\u201C\u201D]([^"\'\u201C\u201D]+)["\'\u201C\u201D]', text)
        if title_match:
            data['title'] = title_match.group(1)
        
        return data
    
    def _parse_website(self, text: str, data: Dict) -> Dict:
        """Parse website citation"""
        # Extract URL
        url_match = re.search(r'https?://[^\s,]+', text)
        if url_match:
            data['url'] = url_match.group()
        
        # Extract access date
        access_match = re.search(r'(?:accessed|retrieved)\s+(.+?)(?:\.|$)', text, re.IGNORECASE)
        if access_match:
            data['access_date'] = access_match.group(1).strip()
        
        # Extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        if year_match:
            data['year'] = year_match.group()
        
        # Author and title
        parts = re.split(r'[,.]', text, maxsplit=2)
        if len(parts) >= 2:
            data['author'] = parts[0].strip()
            title = parts[1].strip()
            title = re.sub(r'^["\'\u201C\u201D\u2018\u2019]+|["\'\u201C\u201D\u2018\u2019]+$', '', title)
            data['title'] = title
        
        # Website name
        if data.get('url'):
            domain_match = re.search(r'://(?:www\.)?([^/]+)', data['url'])
            if domain_match:
                data['website_name'] = domain_match.group(1)
        
        return data
    
    def _parse_chapter(self, text: str, data: Dict) -> Dict:
        """Parse book chapter citation"""
        # Similar to book, but with editor info
        data = self._parse_book(text, data)
        
        # Extract editor
        editor_match = re.search(r'(?:edited by|ed\.|eds\.)\s+([^,.(]+)', text, re.IGNORECASE)
        if editor_match:
            data['editor'] = editor_match.group(1).strip()
        
        # Extract book title (usually after "in")
        book_match = re.search(r'\bin\s+(.+?)(?:,|\(|ed\.)', text, re.IGNORECASE)
        if book_match:
            data['book_title'] = book_match.group(1).strip()
        
        return data


# Example usage and testing
if __name__ == "__main__":
    parser = CitationParser()
    
    test_citations = [
        "Eric Caplan, Mind Games, 1998",
        'John Smith, "The Future of AI," Journal of Computer Science, vol. 45, no. 2 (2023): 123-145.',
        'Jane Doe, "Breaking News," New York Times, January 15, 2024.',
        'Bob Johnson, "Introduction," in The Big Book, ed. Alice Williams (New York: Publisher, 2020), 1-25.',
        'Example Site, "Article Title," https://www.example.com/article, accessed January 1, 2024.',
    ]
    
    for citation in test_citations:
        result = parser.parse_citation(citation)
        print(f"\nOriginal: {citation}")
        print(f"Type: {result['source_type']}")
        print(f"Parsed: {result}")
