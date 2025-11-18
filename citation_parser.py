"""
Citation Parser - Simple version that preserves original text
"""
import re

class CitationParser:
    def __init__(self):
        # Journal indicators
        self.journal_indicators = [
            'Journal', 'Review', 'Quarterly', 'Studies', 'American', 'International',
            'Proceedings', 'Annals', 'Bulletin', 'Letters', 'Research', 'Science',
            'Quarterly', 'Monthly', 'Weekly', 'Rural America', 'Urban', 'Economic',
            'Political', 'Social', 'Medical', 'Clinical', 'Nature', 'Cell'
        ]
        
        # Website indicators
        self.website_indicators = [
            '.com', '.org', '.edu', '.gov', '.net', 'http://', 'https://', 'www.',
            'accessed', 'retrieved', 'available at', 'online', 'Accessed'
        ]
        
        # Newspaper indicators
        self.newspaper_indicators = [
            'Times', 'Post', 'Tribune', 'Chronicle', 'Gazette', 'Herald',
            'Daily', 'Weekly', 'Sunday', 'Morning', 'Evening', 'Star', 'Sun', 'News',
            'Telegraph', 'Guardian', 'Observer', 'Independent', 'Express'
        ]
    
    def parse_citation(self, text):
        """
        Parse a citation minimally, preserving the original text
        Main goal is to identify the source type correctly
        """
        text = text.strip()
        
        # Always preserve the full raw text
        result = {
            'raw_text': text,
            'source_type': 'unknown'
        }
        
        # Detect source type
        source_type = self.detect_source_type(text)
        result['source_type'] = source_type
        
        # Extract year if present
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', text)
        if year_match:
            result['year'] = year_match.group()
        
        # Extract URL if website
        if source_type == 'website':
            url_match = re.search(r'https?://[^\s,]+', text)
            if url_match:
                result['url'] = url_match.group().rstrip('.,;')
        
        return result
    
    def detect_source_type(self, text):
        """Detect the type of source based on text patterns"""
        text_lower = text.lower()
        
        # Check for website first (most specific)
        if any(indicator in text_lower for indicator in self.website_indicators):
            return 'website'
        
        # Check for journal/article patterns
        # Strong journal indicators: volume(issue) or volume:issue patterns
        if re.search(r'\b\d+:\d+|\b\d+\s*\(\d+\)|vol\.\s*\d+|no\.\s*\d+', text_lower):
            return 'journal'
        
        # Pattern like "Rural America 17:4" or "Nature 451"
        if re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+\d+:\d+', text):
            return 'journal'
        
        # Check if it has article title in quotes + journal indicators
        if '"' in text:
            for indicator in self.journal_indicators:
                if indicator in text and re.search(r':\s*\d+[-–]\d+|pp?\.\s*\d+', text):
                    return 'journal'
        
        # Check for newspaper (has specific date + newspaper name)
        for indicator in self.newspaper_indicators:
            if indicator in text:
                # Newspapers often have full dates
                if re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+', text):
                    return 'newspaper_article'
        
        # Check for book patterns
        # Pattern: (Place: Publisher, Year)
        if re.search(r'\([^)]*:.*\d{4}\)', text):
            return 'book'
        
        # If it has a publisher pattern but no journal/newspaper indicators
        if re.search(r'\b(Press|Publishers?|Publishing|Books?|Publications?)\b', text):
            return 'book'
        
        # If it has a year and doesn't match other patterns, likely a book
        if re.search(r'\b(19\d{2}|20\d{2})\b', text) and '"' not in text_lower:
            return 'book'
        
        # Default for academic-looking citations with years
        if re.search(r'\b(19\d{2}|20\d{2})\b', text):
            # If it has quotes around a title, check what follows
            if '"' in text:
                # If quotes are followed by what looks like a journal name
                after_quotes = text.split('"')[-1]
                if any(ind in after_quotes for ind in self.journal_indicators):
                    return 'journal'
            return 'book'
        
        return 'unknown'
