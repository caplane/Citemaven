"""
Enhanced Citation Creator - Optimized for Minimal Input
Transforms minimal citations (LastName, Keywords) into complete academic citations
"""
import re
import requests
from typing import Dict, Optional

class EnhancedCitationCreator:
    def __init__(self):
        # Fallback database for common academic books (when API fails or doesn't have the book)
        self.book_database = {
            # Psychology/Psychiatry books
            'caplan mind games': {
                'author': 'Eric Caplan',
                'title': 'Mind Games: American Culture and the Birth of Psychotherapy',
                'place': 'Berkeley',
                'publisher': 'University of California Press',
                'year': '1998'
            },
            'scull desperate remedies': {
                'author': 'Andrew Scull',
                'title': 'Desperate Remedies: Psychiatry\'s Turbulent Quest to Cure Mental Illness',
                'place': 'Cambridge, MA',
                'publisher': 'Harvard University Press',
                'year': '2022'
            },
            'aviv strangers': {
                'author': 'Rachel Aviv',
                'title': 'Strangers to Ourselves: Unsettled Minds and the Stories That Make Us',
                'place': 'New York',
                'publisher': 'Farrar, Straus and Giroux',
                'year': '2022'
            },
            # History books
            'darity from here': {
                'author': 'William A. Darity Jr. and A. Kirsten Mullen',
                'title': 'From Here to Equality: Reparations for Black Americans in the Twenty-First Century',
                'place': 'Chapel Hill',
                'publisher': 'University of North Carolina Press',
                'year': '2020'
            },
            'du bois black reconstruction': {
                'author': 'W. E. B. Du Bois',
                'title': 'Black Reconstruction in America',
                'place': 'New York',
                'publisher': 'Harcourt, Brace & Co.',
                'year': '1935'
            },
            # Add more books as needed
        }
        
        # Common first names for author completion
        self.author_first_names = {
            'caplan': 'Eric',
            'scull': 'Andrew',
            'aviv': 'Rachel',
            'rachel': 'Rachel Aviv',  # Handle first name only
            'darity': 'William A.',
            'mullen': 'A. Kirsten',
            'du bois': 'W. E. B.',
            'dubois': 'W. E. B.',
            'klerman': 'Gerald L.',
            'stone': 'Alan A.',
            'hollinger': 'David A.',
            'baldwin': 'James',
            'morrison': 'Toni',
            'coates': 'Ta-Nehisi',
        }
        
        # Enhanced publisher database
        self.publisher_places = {
            'Harvard University Press': 'Cambridge, MA',
            'MIT Press': 'Cambridge, MA',
            'Yale University Press': 'New Haven',
            'Princeton University Press': 'Princeton',
            'Stanford University Press': 'Stanford',
            'University of California Press': 'Berkeley',
            'University of Chicago Press': 'Chicago',
            'Columbia University Press': 'New York',
            'University of North Carolina Press': 'Chapel Hill',
            'UNC Press': 'Chapel Hill',
            'Oxford University Press': 'Oxford',
            'Cambridge University Press': 'Cambridge',
            'Farrar, Straus and Giroux': 'New York',
            'Random House': 'New York',
            'Penguin': 'New York',
            'Norton': 'New York',
            'Basic Books': 'New York',
            'Knopf': 'New York',
            'HarperCollins': 'New York',
            'Simon & Schuster': 'New York',
            'Little, Brown': 'Boston',
            'Beacon Press': 'Boston',
            'Routledge': 'London',
            'Verso': 'London',
            'Bloomsbury': 'London',
        }
    
    def parse_minimal_citation(self, text: str) -> Dict[str, str]:
        """Parse minimal citation like 'Caplan, Mind Games' or 'Scull, desperate remedies'"""
        text = text.strip()
        
        # Remove leading numbers
        text = re.sub(r'^\d+\s*', '', text)
        
        result = {
            'original': text,
            'author_last': '',
            'title_keywords': '',
            'full_author': '',
            'year': None
        }
        
        # Try to extract year if present
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        if year_match:
            result['year'] = year_match.group()
            text = text.replace(year_match.group(), '').strip()
        
        # Parse author and title
        if ',' in text:
            parts = text.split(',', 1)
            author_part = parts[0].strip()
            title_part = parts[1].strip() if len(parts) > 1 else ''
            
            # Clean up author
            result['author_last'] = author_part
            
            # Try to get full author name
            author_lower = author_part.lower()
            if author_lower in self.author_first_names:
                result['full_author'] = self.author_first_names[author_lower] + ' ' + author_part.capitalize()
            else:
                # Check if it's just a first name
                if author_lower in ['rachel', 'james', 'toni']:
                    if author_lower in self.author_first_names:
                        result['full_author'] = self.author_first_names[author_lower]
                else:
                    result['full_author'] = author_part
            
            # Clean up title keywords
            result['title_keywords'] = title_part.strip('"\'').strip()
        else:
            # No comma, treat whole thing as title keywords
            result['title_keywords'] = text
        
        return result
    
    def lookup_in_database(self, author_last: str, title_keywords: str) -> Optional[Dict]:
        """Look up in local database first"""
        # Create search key
        search_key = f"{author_last.lower()} {title_keywords.lower()}".strip()
        
        # Try exact match
        if search_key in self.book_database:
            return self.book_database[search_key]
        
        # Try partial matches
        for key, book in self.book_database.items():
            # Check if both author and title keywords match
            if author_last.lower() in key and title_keywords.lower() in key:
                return book
            # Check if just title keywords match (sometimes that's enough)
            if len(title_keywords) > 3 and title_keywords.lower() in key:
                return book
        
        return None
    
    def lookup_openlibrary(self, author: str, title: str, year: Optional[str] = None) -> Optional[Dict]:
        """Look up in Open Library API"""
        try:
            query = f"{author} {title}".strip()
            
            response = requests.get(
                'https://openlibrary.org/search.json',
                params={'q': query, 'limit': 5},
                timeout=5
            )
            
            if response.ok:
                data = response.json()
                if data.get('docs'):
                    # Try to find best match
                    best_doc = None
                    
                    for doc in data['docs']:
                        # Check if author matches
                        doc_authors = doc.get('author_name', [])
                        if doc_authors:
                            doc_author = doc_authors[0].lower()
                            if author.lower() in doc_author or doc_author in author.lower():
                                # Check year if we have one
                                if year and doc.get('first_publish_year'):
                                    if abs(int(year) - int(doc['first_publish_year'])) <= 2:
                                        best_doc = doc
                                        break
                                elif not best_doc:
                                    best_doc = doc
                    
                    if not best_doc and data['docs']:
                        best_doc = data['docs'][0]
                    
                    if best_doc:
                        # Extract publisher info
                        publishers = best_doc.get('publisher', [])
                        publisher = publishers[0] if publishers else None
                        
                        # Get place from publisher
                        place = None
                        if publisher:
                            place = self.publisher_places.get(publisher)
                            if not place:
                                places = best_doc.get('publish_place', [])
                                place = places[0] if places else None
                        
                        return {
                            'author': best_doc.get('author_name', [author])[0],
                            'title': best_doc.get('title', title),
                            'publisher': publisher,
                            'place': place,
                            'year': best_doc.get('first_publish_year', year)
                        }
        except Exception as e:
            print(f"API lookup failed: {e}")
        
        return None
    
    def create_citation(self, text: str, style: str = 'chicago') -> str:
        """Create a complete citation from minimal input"""
        # Parse the minimal citation
        parsed = self.parse_minimal_citation(text)
        
        # Try local database first
        book_data = self.lookup_in_database(parsed['author_last'], parsed['title_keywords'])
        
        # If not in database, try API
        if not book_data:
            author_to_search = parsed['full_author'] or parsed['author_last']
            book_data = self.lookup_openlibrary(
                author_to_search,
                parsed['title_keywords'],
                parsed['year']
            )
        
        # If we found data, format it
        if book_data:
            return self.format_citation(book_data, style)
        else:
            # Return original with basic formatting
            return f"{parsed['full_author'] or parsed['author_last']}, <em>{parsed['title_keywords']}</em>."
    
    def format_citation(self, data: Dict, style: str = 'chicago') -> str:
        """Format citation data according to style"""
        if style == 'chicago':
            # Chicago format: Author, Title (Place: Publisher, Year).
            citation = data['author']
            
            # Add title with italics
            if data.get('title'):
                citation += f", <em>{data['title']}</em>"
            
            # Add publication info
            pub_parts = []
            if data.get('place'):
                pub_parts.append(data['place'])
            if data.get('publisher'):
                if pub_parts:
                    pub_parts[0] += f": {data['publisher']}"
                else:
                    pub_parts.append(data['publisher'])
            if data.get('year'):
                if pub_parts:
                    pub_parts.append(str(data['year']))
                else:
                    pub_parts = [str(data['year'])]
            
            if pub_parts:
                citation += f" ({', '.join(pub_parts)})"
            
            citation += '.'
            return citation
        
        # Add other styles as needed
        return self.format_citation(data, 'chicago')  # Default to Chicago

# Export for use in app
citation_creator = EnhancedCitationCreator()

def process_minimal_citation(text: str, style: str = 'chicago') -> str:
    """Process a single minimal citation"""
    return citation_creator.create_citation(text, style)
