"""
Citation Formatter - Final version that preserves original formatting
"""
import re

class CitationFormatter:
    def __init__(self):
        pass
    
    def format_citation(self, parsed, style='chicago'):
        """Format a parsed citation in the specified style"""
        raw_text = parsed.get('raw_text', '')
        if not raw_text:
            return ''
        
        # Clean up the text first
        text = self.clean_citation(raw_text)
        
        # Apply style-specific formatting
        if style.lower() == 'chicago':
            return self.format_chicago_simple(text, parsed)
        elif style.lower() == 'mla':
            return self.format_mla_simple(text, parsed)
        elif style.lower() == 'apa':
            return self.format_apa_simple(text, parsed)
        else:
            return text
    
    def clean_citation(self, text):
        """Clean up a citation minimally"""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Ensure ends with period
        if text and not text[-1] in '.!?':
            text += '.'
        
        return text
    
    def format_chicago_simple(self, text, parsed):
        """
        Apply Chicago formatting to raw text
        Main goal: Add italics for book/journal titles while preserving everything else
        """
        source_type = parsed.get('source_type', 'unknown')
        
        if source_type == 'book':
            # For books: italicize the title
            # Title is usually after author, before (Place: Publisher) or before year
            
            # First check if title is in quotes (convert to italics)
            if '"' in text:
                text = re.sub(r'["""]([^"""]+)["""]', r'<em>\1</em>', text)
            else:
                # Try to identify title between author and publication info
                # Pattern: Author, Title (Place: Publisher
                pattern = r'^([^,]+,)\s+([A-Z][^,()\[\]]+?)(\s*\([^)]+\))'
                match = re.search(pattern, text)
                if match:
                    title = match.group(2).strip()
                    # Make sure it's a real title (multiple words, not just a place)
                    if len(title.split()) > 1 and '<em>' not in text:
                        text = text.replace(title, f'<em>{title}</em>')
        
        elif source_type == 'journal':
            # For journals: keep article title in quotes, italicize journal name
            
            # Pattern 1: "Article Title," Journal Name Volume
            pattern1 = r'"[^"]+",?\s*([A-Z][^,\d]+?)\s+(\d+)'
            match1 = re.search(pattern1, text)
            if match1:
                journal_name = match1.group(1).strip()
                if journal_name and '<em>' not in journal_name:
                    text = text.replace(journal_name, f'<em>{journal_name}</em>')
            
            # Pattern 2: "Article Title" (Journal Name Volume:Issue)
            else:
                pattern2 = r'"[^"]+"\s*\(([^)]+?\s+\d+:\d+)'
                match2 = re.search(pattern2, text)
                if match2:
                    journal_info = match2.group(1)
                    # Extract just the journal name (before the numbers)
                    journal_match = re.match(r'([A-Z][^0-9]+?)\s+\d+:', journal_info)
                    if journal_match:
                        journal_name = journal_match.group(1).strip()
                        if journal_name and '<em>' not in journal_name:
                            # Replace in the original text, preserving the parentheses
                            text = text.replace(f'({journal_info}', f'(<em>{journal_name}</em> {journal_info[len(journal_name)+1:]}')
        
        elif source_type == 'newspaper_article':
            # For newspapers: keep article title in quotes, italicize newspaper name
            # Pattern: "Article Title," Newspaper Name, Date
            pattern = r'"[^"]+",?\s*([A-Z][^,]+?),?\s*(January|February|March|April|May|June|July|August|September|October|November|December|\d{4})'
            match = re.search(pattern, text)
            if match:
                newspaper_name = match.group(1).strip()
                if newspaper_name and '<em>' not in text:
                    text = text.replace(newspaper_name, f'<em>{newspaper_name}</em>')
        
        elif source_type == 'website':
            # For websites: article title in quotes (if present), website name in italics
            # Try to identify website name after title
            if '"' in text:
                # Pattern: "Title," Website, Date
                pattern = r'"[^"]+",?\s*([A-Z][^,]+?)[,.]?\s*(?:\d{4}|January|February|March|April|May|June|July|August|September|October|November|December|Accessed|Available)'
                match = re.search(pattern, text)
                if match:
                    website_name = match.group(1).strip()
                    # Don't italicize if it looks like an author name
                    if website_name and not re.match(r'^[A-Z][a-z]+\s+[A-Z]', website_name):
                        text = text.replace(website_name, f'<em>{website_name}</em>')
            else:
                # No quotes, look for website name before year/URL
                pattern = r'^([^,]+?),\s*([A-Z][^,]+?)[,.]?\s*\d{4}'
                match = re.search(pattern, text)
                if match:
                    org_name = match.group(1).strip()
                    title_or_site = match.group(2).strip()
                    # The second part is likely the title/website
                    if title_or_site and '<em>' not in text:
                        text = text.replace(title_or_site, f'<em>{title_or_site}</em>')
        
        return text
    
    def format_mla_simple(self, text, parsed):
        """MLA formatting - similar to Chicago for now"""
        return self.format_chicago_simple(text, parsed)
    
    def format_apa_simple(self, text, parsed):
        """APA formatting - similar approach but different rules"""
        source_type = parsed.get('source_type', 'unknown')
        
        if source_type == 'book':
            # In APA, book titles are italicized
            if '"' in text:
                text = re.sub(r'["""]([^"""]+)["""]', r'<em>\1</em>', text)
            else:
                # Find title after year
                pattern = r'\((\d{4})\)[,.]?\s*([A-Z][^,()\[\]]+?)(?:\.|,|\s*\()'
                match = re.search(pattern, text)
                if match:
                    title = match.group(2).strip()
                    if len(title.split()) > 1 and '<em>' not in text:
                        text = text.replace(title, f'<em>{title}</em>')
        
        elif source_type == 'journal':
            # In APA: journal name and volume in italics, article title plain
            # Remove quotes from article title if present
            text = re.sub(r'["""]([^"""]+)["""]', r'\1', text)
            
            # Find journal name and italicize with volume
            pattern = r'\.\s+([A-Z][^,]+?),?\s+(\d+)'
            match = re.search(pattern, text)
            if match:
                journal_name = match.group(1).strip()
                volume = match.group(2)
                old_text = f'{journal_name}, {volume}'
                new_text = f'<em>{journal_name}, {volume}</em>'
                text = text.replace(old_text, new_text)
        
        return text
