"""
Citation Formatter - Enhanced to match professional style guide
"""
import re

class CitationFormatter:
    def __init__(self):
        pass
    
    def format_citation(self, parsed, style='chicago'):
        """Format a parsed citation in the specified style"""
        if style.lower() == 'chicago':
            return self.format_chicago(parsed)
        elif style.lower() == 'mla':
            return self.format_mla(parsed)
        elif style.lower() == 'apa':
            return self.format_apa(parsed)
        else:
            # If unparsed, at least clean up the raw text
            return self.clean_raw_citation(parsed.get('raw_text', ''))
    
    def clean_raw_citation(self, text):
        """Clean up raw citation text minimally"""
        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        # Ensure it ends with a period
        if text and not text[-1] in '.!?':
            text += '.'
        return text
    
    def format_chicago(self, parsed):
        """Format citation in Chicago style"""
        source_type = parsed.get('source_type', 'unknown')
        
        if source_type == 'book':
            return self._chicago_book(parsed)
        elif source_type == 'journal':
            return self._chicago_journal(parsed)
        elif source_type == 'website':
            return self._chicago_website(parsed)
        else:
            # For unknown types, try to preserve as much as possible
            return self.clean_raw_citation(parsed.get('raw_text', ''))
    
    def format_author_chicago(self, authors):
        """Format authors in Chicago style (Last, First for first author)"""
        if not authors:
            return ""
        
        formatted_authors = []
        for i, author in enumerate(authors):
            author = author.strip()
            if not author:
                continue
                
            # For first author, use Last, First format
            if i == 0:
                # Check if already in Last, First format
                if ',' in author:
                    formatted_authors.append(author)
                else:
                    # Split name and reformat
                    parts = author.split()
                    if len(parts) >= 2:
                        # Assume last part is surname
                        last = parts[-1]
                        first_middle = ' '.join(parts[:-1])
                        formatted_authors.append(f"{last}, {first_middle}")
                    else:
                        formatted_authors.append(author)
            else:
                # Additional authors in First Last format
                formatted_authors.append(author)
        
        # Join multiple authors
        if len(formatted_authors) == 1:
            return formatted_authors[0]
        elif len(formatted_authors) == 2:
            return f"{formatted_authors[0]} and {formatted_authors[1]}"
        else:
            # For 3+ authors, use et al. after first author
            return f"{formatted_authors[0]}, et al."
    
    def _chicago_book(self, p):
        """Chicago style for books - matching model document"""
        parts = []
        
        # Author(s)
        if p.get('authors'):
            author_str = self.format_author_chicago(p['authors'])
            if author_str:
                parts.append(author_str)
        
        # Title (italicized) - preserve full title
        if p.get('title'):
            # Clean up the title
            title = p['title'].strip()
            # Remove quotes if present
            title = title.strip('"').strip("'")
            parts.append(f"<em>{title}</em>")
        elif p.get('raw_text'):
            # Try to extract title from raw text if not parsed
            import re
            # Look for text in quotes or after author before year/publisher
            title_match = re.search(r'["""]([^"""]+)["""]', p['raw_text'])
            if not title_match:
                # Try to find title between author and publication info
                title_match = re.search(r'[,.]?\s*([A-Z][^,()\[\]]+?)(?:\s*\(|\s*,\s*\d{4})', p['raw_text'])
            if title_match:
                title = title_match.group(1).strip()
                parts.append(f"<em>{title}</em>")
        
        # Editor if present
        if p.get('editor'):
            parts[-1] += f", ed. {p['editor']}"
        
        # Publication info (Place: Publisher, Year)
        pub_info = []
        
        # Place and publisher
        place_pub = []
        if p.get('place'):
            place_pub.append(p['place'].strip())
        if p.get('publisher'):
            if place_pub:
                # Combine as Place: Publisher
                pub_info.append(f"{place_pub[0]}: {p['publisher'].strip()}")
            else:
                pub_info.append(p['publisher'].strip())
        elif place_pub:
            pub_info.append(place_pub[0])
        
        # Year
        if p.get('year'):
            year_str = p['year'].strip()
            # Clean year (remove parentheses if present)
            year_str = year_str.strip('()')
            if pub_info:
                pub_info.append(year_str)
            else:
                pub_info.append(year_str)
        
        # Combine publication info in parentheses
        if pub_info:
            if len(pub_info) == 2 and ':' in pub_info[0]:
                # Format: (Place: Publisher, Year)
                parts.append(f"({pub_info[0]}, {pub_info[1]})")
            elif len(pub_info) == 2:
                # Format: (Publisher, Year) or (Place, Year)
                parts.append(f"({pub_info[0]}, {pub_info[1]})")
            elif len(pub_info) == 1:
                # Just year or publisher
                parts.append(f"({pub_info[0]})")
        
        # Page numbers
        if p.get('pages'):
            parts.append(p['pages'].strip())
        elif p.get('page'):
            parts.append(p['page'].strip())
        
        # Join with appropriate punctuation
        result = ""
        for i, part in enumerate(parts):
            if i == 0:
                result = part
            elif part.startswith('('):
                # Publication info gets a space but no comma
                result += f" {part}"
            else:
                # Everything else gets comma separation
                result += f", {part}"
        
        # Ensure ends with period
        if result and not result[-1] in '.!?':
            result += '.'
        
        return result
    
    def _chicago_journal(self, p):
        """Chicago style for journal articles - matching model document"""
        parts = []
        
        # Author(s)
        if p.get('authors'):
            author_str = self.format_author_chicago(p['authors'])
            if author_str:
                parts.append(author_str)
        
        # Article title in quotes
        if p.get('title'):
            title = p['title'].strip().strip('"').strip("'")
            parts.append(f'"{title}"')
        
        # Journal name in italics
        journal_parts = []
        if p.get('journal'):
            journal = p['journal'].strip()
            journal_parts.append(f"<em>{journal}</em>")
        
        # Volume and issue
        if p.get('volume'):
            vol = p['volume'].strip()
            journal_parts.append(vol)
            if p.get('issue'):
                issue = p['issue'].strip()
                # Format: vol, no. # 
                journal_parts[-1] += f", no. {issue}"
        
        # Date in parentheses
        if p.get('year'):
            year = p['year'].strip()
            # Check if we have month/date info
            if p.get('date'):
                journal_parts.append(f"({p['date']})")
            else:
                journal_parts.append(f"({year})")
        
        # Join journal parts
        if journal_parts:
            if len(journal_parts) == 1:
                parts.append(journal_parts[0])
            elif len(journal_parts) == 2:
                parts.append(f"{journal_parts[0]} {journal_parts[1]}")
            elif len(journal_parts) == 3:
                # Journal vol (date)
                parts.append(f"{journal_parts[0]} {journal_parts[1]} {journal_parts[2]}")
        
        # Pages with colon
        if p.get('pages'):
            pages = p['pages'].strip()
            # Add colon before page numbers
            if parts and journal_parts:
                parts[-1] += f": {pages}"
            else:
                parts.append(pages)
        
        # DOI or URL if present
        if p.get('doi'):
            parts.append(f"https://doi.org/{p['doi']}")
        elif p.get('url'):
            parts.append(p['url'])
        
        # Join with appropriate punctuation
        result = ". ".join(parts)
        
        # Ensure ends with period
        if result and not result[-1] in '.!?':
            result += '.'
        
        return result
    
    def _chicago_website(self, p):
        """Chicago style for websites - matching model document"""
        parts = []
        
        # Author or organization
        if p.get('authors'):
            author_str = self.format_author_chicago(p['authors'])
            if author_str:
                parts.append(author_str)
        elif p.get('organization'):
            parts.append(p['organization'])
        
        # Title in quotes
        if p.get('title'):
            title = p['title'].strip().strip('"').strip("'")
            parts.append(f'"{title}"')
        
        # Website name in italics
        if p.get('website'):
            website = p['website'].strip()
            # Clean up website name (remove .com, www., etc.)
            website = re.sub(r'^(www\.|https?://)', '', website)
            website = re.sub(r'\.(com|org|net|gov|edu)/?.*$', '', website)
            # Capitalize properly
            website = website.replace('-', ' ').replace('_', ' ')
            website = ' '.join(word.capitalize() for word in website.split())
            parts.append(f"<em>{website}</em>")
        
        # Publication date if different from access date
        if p.get('pub_date'):
            parts.append(p['pub_date'])
        
        # Access date
        if p.get('access_date'):
            parts.append(f"Accessed {p['access_date']}")
        
        # URL
        if p.get('url'):
            url = p['url'].strip()
            # Ensure URL starts with http
            if not url.startswith('http'):
                url = 'https://' + url
            parts.append(url)
        
        # Join with appropriate punctuation
        result = ". ".join(parts)
        
        # Ensure ends with period
        if result and not result.endswith('.') and not result.endswith('/'):
            result += '.'
        
        return result
    
    def format_mla(self, parsed):
        """Format citation in MLA style"""
        source_type = parsed.get('source_type', 'unknown')
        
        if source_type == 'book':
            return self._mla_book(parsed)
        elif source_type == 'journal':
            return self._mla_journal(parsed)
        elif source_type == 'website':
            return self._mla_website(parsed)
        else:
            return self.clean_raw_citation(parsed.get('raw_text', ''))
    
    def _mla_book(self, p):
        """MLA style for books"""
        parts = []
        
        # Author (Last, First)
        if p.get('authors'):
            author = p['authors'][0]
            if ', ' not in author:
                name_parts = author.split()
                if len(name_parts) >= 2:
                    author = f"{name_parts[-1]}, {' '.join(name_parts[:-1])}"
            parts.append(author)
        
        # Title in italics
        if p.get('title'):
            title = p['title'].strip().strip('"').strip("'")
            parts.append(f"<em>{title}</em>")
        
        # Publisher
        if p.get('publisher'):
            parts.append(p['publisher'].strip())
        
        # Year
        if p.get('year'):
            parts.append(p['year'].strip())
        
        # Join with appropriate punctuation
        result = ". ".join(parts)
        if result and not result[-1] in '.!?':
            result += '.'
        
        return result
    
    def _mla_journal(self, p):
        """MLA style for journal articles"""
        parts = []
        
        # Author (Last, First)
        if p.get('authors'):
            author = p['authors'][0]
            if ', ' not in author:
                name_parts = author.split()
                if len(name_parts) >= 2:
                    author = f"{name_parts[-1]}, {' '.join(name_parts[:-1])}"
            parts.append(author)
        
        # Article title in quotes
        if p.get('title'):
            title = p['title'].strip().strip('"').strip("'")
            parts.append(f'"{title}"')
        
        # Journal name in italics
        if p.get('journal'):
            journal = p['journal'].strip()
            journal_str = f"<em>{journal}</em>"
            
            # Add volume and issue
            if p.get('volume'):
                journal_str += f", vol. {p['volume']}"
                if p.get('issue'):
                    journal_str += f", no. {p['issue']}"
            
            # Add year
            if p.get('year'):
                journal_str += f", {p['year']}"
            
            # Add pages
            if p.get('pages'):
                journal_str += f", pp. {p['pages']}"
            
            parts.append(journal_str)
        
        # Join with appropriate punctuation
        result = ". ".join(parts)
        if result and not result[-1] in '.!?':
            result += '.'
        
        return result
    
    def _mla_website(self, p):
        """MLA style for websites"""
        parts = []
        
        # Author (if present)
        if p.get('authors'):
            author = p['authors'][0]
            if ', ' not in author and ' ' in author:
                name_parts = author.split()
                author = f"{name_parts[-1]}, {' '.join(name_parts[:-1])}"
            parts.append(author)
        
        # Title in quotes
        if p.get('title'):
            title = p['title'].strip().strip('"').strip("'")
            parts.append(f'"{title}"')
        
        # Website in italics
        if p.get('website'):
            website = p['website'].strip()
            website = re.sub(r'^(www\.|https?://)', '', website)
            website = re.sub(r'\.(com|org|net|gov|edu)/?.*$', '', website)
            website = ' '.join(word.capitalize() for word in website.replace('-', ' ').split())
            parts.append(f"<em>{website}</em>")
        
        # Date
        if p.get('pub_date'):
            parts.append(p['pub_date'])
        
        # URL
        if p.get('url'):
            parts.append(p['url'])
        
        # Access date
        if p.get('access_date'):
            parts.append(f"Accessed {p['access_date']}")
        
        # Join with appropriate punctuation
        result = ". ".join(parts)
        if result and not result[-1] in '.!?':
            result += '.'
        
        return result
    
    def format_apa(self, parsed):
        """Format citation in APA style"""
        source_type = parsed.get('source_type', 'unknown')
        
        if source_type == 'book':
            return self._apa_book(parsed)
        elif source_type == 'journal':
            return self._apa_journal(parsed)
        elif source_type == 'website':
            return self._apa_website(parsed)
        else:
            return self.clean_raw_citation(parsed.get('raw_text', ''))
    
    def _apa_book(self, p):
        """APA style for books"""
        parts = []
        
        # Author (Last, F. M.)
        if p.get('authors'):
            author = p['authors'][0]
            if ', ' not in author:
                name_parts = author.split()
                if len(name_parts) >= 2:
                    # Get initials
                    initials = '. '.join([n[0].upper() for n in name_parts[:-1]]) + '.'
                    author = f"{name_parts[-1]}, {initials}"
            parts.append(author)
        
        # Year in parentheses
        if p.get('year'):
            parts.append(f"({p['year'].strip()})")
        
        # Title in italics (sentence case)
        if p.get('title'):
            title = p['title'].strip()
            # Convert to sentence case (capitalize only first word and proper nouns)
            if title:
                words = title.split()
                sentence_case = words[0].capitalize()
                if len(words) > 1:
                    sentence_case += ' ' + ' '.join(words[1:]).lower()
                parts.append(f"<em>{sentence_case}</em>")
        
        # Publisher
        if p.get('publisher'):
            parts.append(p['publisher'].strip())
        
        # Join with appropriate punctuation
        result = ". ".join(parts)
        if result and not result[-1] in '.!?':
            result += '.'
        
        return result
    
    def _apa_journal(self, p):
        """APA style for journal articles"""
        parts = []
        
        # Author (Last, F. M.)
        if p.get('authors'):
            author = p['authors'][0]
            if ', ' not in author and ' ' in author:
                name_parts = author.split()
                initials = '. '.join([n[0].upper() for n in name_parts[:-1]]) + '.'
                author = f"{name_parts[-1]}, {initials}"
            parts.append(author)
        
        # Year in parentheses
        if p.get('year'):
            parts.append(f"({p['year'].strip()})")
        
        # Title (sentence case, no quotes)
        if p.get('title'):
            title = p['title'].strip()
            words = title.split()
            if words:
                sentence_case = words[0].capitalize()
                if len(words) > 1:
                    sentence_case += ' ' + ' '.join(words[1:]).lower()
                parts.append(sentence_case)
        
        # Journal in italics with volume
        if p.get('journal'):
            journal_str = f"<em>{p['journal']}"
            if p.get('volume'):
                journal_str += f", {p['volume']}"
            if p.get('issue'):
                journal_str += f"({p['issue']})"
            journal_str += "</em>"
            
            if p.get('pages'):
                journal_str += f", {p['pages']}"
            
            parts.append(journal_str)
        
        # DOI if present
        if p.get('doi'):
            parts.append(f"https://doi.org/{p['doi']}")
        
        # Join with appropriate punctuation
        result = ". ".join(parts)
        if result and not result[-1] in '.!?':
            result += '.'
        
        return result
    
    def _apa_website(self, p):
        """APA style for websites"""
        parts = []
        
        # Author or organization
        if p.get('authors'):
            author = p['authors'][0]
            if ', ' not in author and ' ' in author:
                name_parts = author.split()
                initials = '. '.join([n[0].upper() for n in name_parts[:-1]]) + '.'
                author = f"{name_parts[-1]}, {initials}"
            parts.append(author)
        elif p.get('organization'):
            parts.append(p['organization'])
        elif p.get('website'):
            # Use website as author if no other author
            website = p['website'].strip()
            website = re.sub(r'^(www\.|https?://)', '', website)
            website = re.sub(r'\.(com|org|net|gov|edu)/?.*$', '', website)
            website = ' '.join(word.capitalize() for word in website.replace('-', ' ').split())
            parts.append(website)
        
        # Date
        if p.get('pub_date'):
            parts.append(f"({p['pub_date']})")
        elif p.get('year'):
            parts.append(f"({p['year']})")
        else:
            parts.append("(n.d.)")
        
        # Title in italics
        if p.get('title'):
            title = p['title'].strip()
            parts.append(f"<em>{title}</em>")
        
        # URL
        if p.get('url'):
            parts.append(p['url'])
        
        # Join with appropriate punctuation
        result = ". ".join(parts)
        if result and not result[-1] in '.!?':
            result += '.'
        
        return result
