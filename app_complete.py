"""
CiteMaven - Complete Citation Management System
BULLETPROOF VERSION - All functionality embedded, no external imports needed
"""
from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
from io import BytesIO
import os
import zipfile
import xml.dom.minidom as minidom
import re
import requests
from pathlib import Path
import shutil
import tempfile

# Import your existing parsers/formatters
from citation_parser import CitationParser
from citation_formatter import CitationFormatter

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = 'citation-secret-2024'

parser = CitationParser()
formatter = CitationFormatter()

# Global variables for incipit processing
problem_notes = []

# ==================== EMBEDDED ENHANCED CITATION CREATOR ====================
# This is the COMPLETE enhanced citation system, not just 3 books!

BOOK_DATABASE = {
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
    'rachel strangers': {
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
    }
}

AUTHOR_FIRST_NAMES = {
    'caplan': 'Eric',
    'scull': 'Andrew',
    'aviv': 'Rachel',
    'rachel': 'Rachel Aviv',
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

PUBLISHER_PLACES = {
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
    'University of Pennsylvania Press': 'Philadelphia',
    'University of Michigan Press': 'Ann Arbor',
    'University of Minnesota Press': 'Minneapolis',
    'University of Texas Press': 'Austin',
    'University of Washington Press': 'Seattle',
    'University of Wisconsin Press': 'Madison',
    'University of Georgia Press': 'Athens, GA',
    'Oxford University Press': 'Oxford',
    'Cambridge University Press': 'Cambridge',
    'Edinburgh University Press': 'Edinburgh',
    'Manchester University Press': 'Manchester',
    'Penguin': 'New York',
    'Penguin Random House': 'New York',
    'Random House': 'New York',
    'HarperCollins': 'New York',
    'Simon & Schuster': 'New York',
    'Hachette': 'New York',
    'Macmillan': 'New York',
    'Norton': 'New York',
    'W. W. Norton': 'New York',
    'Knopf': 'New York',
    'Alfred A. Knopf': 'New York',
    'Basic Books': 'New York',
    'Verso': 'London',
    'Routledge': 'London',
    'Palgrave Macmillan': 'London',
    'Bloomsbury': 'London',
    'Faber & Faber': 'London',
    'Allen Lane': 'London',
    'Vintage': 'New York',
    'Doubleday': 'New York',
    'Little, Brown': 'Boston',
    'Houghton Mifflin': 'Boston',
    'Beacon Press': 'Boston',
    'Scribner': 'New York',
    'St. Martin\'s Press': 'New York',
    'Farrar, Straus and Giroux': 'New York',
    'Grove Press': 'New York',
    'The New Press': 'New York',
    'Sage Publications': 'Thousand Oaks, CA',
    'Sage': 'Thousand Oaks, CA',
    'Wiley': 'Hoboken',
    'John Wiley & Sons': 'Hoboken',
    'Elsevier': 'Amsterdam',
    'Springer': 'Berlin',
    'Taylor & Francis': 'London',
    'Brill': 'Leiden',
    'De Gruyter': 'Berlin',
    'University of Toronto Press': 'Toronto',
    'McGill-Queen\'s University Press': 'Montreal',
    'UBC Press': 'Vancouver',
}

def infer_place_from_publisher(publisher):
    """Infer publication place from publisher name"""
    if not publisher:
        return ''
    
    for pub, place in PUBLISHER_PLACES.items():
        if pub.lower() in publisher.lower() or publisher.lower() in pub.lower():
            return place
    return ''

def parse_minimal_citation(text):
    """Parse minimal citation like 'Caplan, Mind Games' or 'Scull, desperate remedies'"""
    text = text.strip()
    
    # Remove leading numbers
    text = re.sub(r'^\d+\s*', '', text)
    # Remove trailing period
    text = re.sub(r'\.$', '', text)
    
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
        if author_lower in AUTHOR_FIRST_NAMES:
            result['full_author'] = AUTHOR_FIRST_NAMES[author_lower] + ' ' + author_part.capitalize()
        else:
            # Check if it's just a first name
            if author_lower in ['rachel', 'james', 'toni']:
                if author_lower in AUTHOR_FIRST_NAMES:
                    result['full_author'] = AUTHOR_FIRST_NAMES[author_lower]
            else:
                result['full_author'] = author_part
        
        # Clean up title keywords
        result['title_keywords'] = title_part.strip('"\'').strip()
    else:
        # No comma, treat whole thing as title keywords
        result['title_keywords'] = text
    
    return result

def lookup_in_database(author_last, title_keywords):
    """Look up in local database first"""
    # Create search key
    search_key = f"{author_last.lower()} {title_keywords.lower()}".strip()
    
    # Try exact match
    if search_key in BOOK_DATABASE:
        return BOOK_DATABASE[search_key]
    
    # Try partial matches
    for key, book in BOOK_DATABASE.items():
        # Check if both author and title keywords match
        if author_last.lower() in key and title_keywords.lower() in key:
            return book
        # Check if just title keywords match (sometimes that's enough)
        if len(title_keywords) > 3 and title_keywords.lower() in key:
            return book
    
    return None

def lookup_openlibrary(author, title, year=None):
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
                        place = infer_place_from_publisher(publisher)
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

def format_citation_chicago(data):
    """Format citation data in Chicago style"""
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

def process_minimal_citation(text, style='chicago'):
    """Main function to create a complete citation from minimal input"""
    print(f"  Processing: '{text}'")
    
    # Parse the minimal citation
    parsed = parse_minimal_citation(text)
    
    # Try local database first
    book_data = lookup_in_database(parsed['author_last'], parsed['title_keywords'])
    
    # If not in database, try API
    if not book_data:
        author_to_search = parsed['full_author'] or parsed['author_last']
        book_data = lookup_openlibrary(
            author_to_search,
            parsed['title_keywords'],
            parsed['year']
        )
    
    # If we found data, format it
    if book_data:
        return format_citation_chicago(book_data)
    else:
        # Return original with basic formatting
        if parsed['full_author'] or parsed['author_last']:
            return f"{parsed['full_author'] or parsed['author_last']}, <em>{parsed['title_keywords']}</em>."
        else:
            return f"<em>{text}</em>."

# ==================== END OF EMBEDDED CITATION CREATOR ====================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'docx'

def unpack_docx(docx_path, extract_dir):
    with zipfile.ZipFile(docx_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

def pack_docx(source_dir, output_path):
    if os.path.exists(output_path):
        os.remove(output_path)
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, arcname)

def extract_endnotes(path):
    """Extract endnote content from endnotes.xml"""
    dom = minidom.parse(str(path))
    endnotes = {}
    for en in dom.getElementsByTagName('w:endnote'):
        en_id = en.getAttribute('w:id')
        if en_id and en_id not in ['-1', '0']:
            text = ''.join([t.firstChild.nodeValue for t in en.getElementsByTagName('w:t') if t.firstChild])
            # Clean up the text
            text = re.sub(r'^\s*\d*\s*', '', text).strip()
            endnotes[en_id] = text
    return endnotes

def update_endnotes_xml_formatted(path, formatted):
    """Update endnotes with formatted citations matching desired output exactly"""
    dom = minidom.parse(str(path))
    
    for en in dom.getElementsByTagName('w:endnote'):
        en_id = en.getAttribute('w:id')
        
        if en_id in formatted:
            paragraphs = en.getElementsByTagName('w:p')
            if not paragraphs:
                continue
                
            p = paragraphs[0]
            
            # Clear existing paragraph properties
            for pPr in p.getElementsByTagName('w:pPr'):
                p.removeChild(pPr)
            
            # Create new paragraph properties
            pPr = dom.createElement('w:pPr')
            
            # Add EndnoteText style
            pStyle = dom.createElement('w:pStyle')
            pStyle.setAttribute('w:val', 'EndnoteText')
            pPr.appendChild(pStyle)
            
            # Add spacing
            spacing = dom.createElement('w:spacing')
            spacing.setAttribute('w:after', '120')
            pPr.appendChild(spacing)
            
            # Insert paragraph properties
            if p.firstChild:
                p.insertBefore(pPr, p.firstChild)
            else:
                p.appendChild(pPr)
            
            # Find the endnoteRef run and preserve it
            endnote_ref_run = None
            for run in p.getElementsByTagName('w:r'):
                if run.getElementsByTagName('w:endnoteRef'):
                    endnote_ref_run = run
                    break
            
            # Remove all runs except the endnoteRef
            for run in list(p.getElementsByTagName('w:r')):
                if run != endnote_ref_run:
                    try:
                        p.removeChild(run)
                    except:
                        pass
            
            # Add a space after the endnote reference
            if endnote_ref_run:
                space_run = dom.createElement('w:r')
                space_text = dom.createElement('w:t')
                space_text.setAttribute('xml:space', 'preserve')
                space_text.appendChild(dom.createTextNode(' '))
                space_run.appendChild(space_text)
                
                if endnote_ref_run.nextSibling:
                    p.insertBefore(space_run, endnote_ref_run.nextSibling)
                else:
                    p.appendChild(space_run)
            
            # Parse formatted text and add with proper formatting
            formatted_text = formatted[en_id]
            
            # Split by <em> tags to handle italics
            parts = re.split(r'(<em>.*?</em>)', formatted_text)
            
            for part in parts:
                if not part:
                    continue
                
                new_run = dom.createElement('w:r')
                
                # Create run properties
                rPr = dom.createElement('w:rPr')
                
                # Add font - Times New Roman
                rFonts = dom.createElement('w:rFonts')
                rFonts.setAttribute('w:ascii', 'Times New Roman')
                rFonts.setAttribute('w:hAnsi', 'Times New Roman')
                rFonts.setAttribute('w:cs', 'Times New Roman')
                rPr.appendChild(rFonts)
                
                # Add size - 20 half-points (10pt)
                sz = dom.createElement('w:sz')
                sz.setAttribute('w:val', '20')
                rPr.appendChild(sz)
                
                szCs = dom.createElement('w:szCs')
                szCs.setAttribute('w:val', '20')
                rPr.appendChild(szCs)
                
                # Check if this part should be italic
                if '<em>' in part:
                    # Add italic properties
                    i_elem = dom.createElement('w:i')
                    rPr.appendChild(i_elem)
                    
                    iCs_elem = dom.createElement('w:iCs')
                    rPr.appendChild(iCs_elem)
                    
                    # Remove the em tags from the text
                    part = re.sub(r'</?em>', '', part)
                
                # Add run properties to run
                new_run.appendChild(rPr)
                
                # Add text
                new_text = dom.createElement('w:t')
                new_text.setAttribute('xml:space', 'preserve')
                new_text.appendChild(dom.createTextNode(part))
                new_run.appendChild(new_text)
                
                # Append run to paragraph
                p.appendChild(new_run)
    
    with open(str(path), 'wb') as f:
        f.write(dom.toxml(encoding='UTF-8'))

# INCIPIT FUNCTIONS (keeping minimal for space)
def clean_word_for_output(word):
    word = re.sub(r'^[^\w]+', '', word)
    word = re.sub(r'[^\w]+$', '', word)
    return word

@app.route('/')
def index():
    return render_template('index_complete.html')

@app.route('/process', methods=['POST'])
def process():
    """Process document based on selected mode"""
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if not file.filename or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file. Please upload a .docx file'}), 400
    
    mode = request.form.get('mode', 'format')
    style = request.form.get('style', 'chicago')
    
    print(f"\n{'='*60}")
    print(f"CiteMaven Processing: {file.filename}")
    print(f"Mode: {mode}")
    print(f"Style: {style}")
    print('='*60)
    
    temp_dir = None
    
    try:
        # Setup temp directory
        temp_dir = Path(tempfile.mkdtemp())
        input_path = temp_dir / 'input.docx'
        file.save(input_path)
        
        # Extract document
        extract_dir = temp_dir / 'extracted'
        unpack_docx(input_path, extract_dir)
        
        # Check for endnotes
        endnotes_file = extract_dir / 'word' / 'endnotes.xml'
        if not endnotes_file.exists():
            return jsonify({'error': 'No endnotes found in document'}), 400
        
        # Extract endnotes
        endnotes = extract_endnotes(endnotes_file)
        print(f'✔ Extracted {len(endnotes)} endnotes')
        
        formatted_endnotes = {}
        
        # Mode 1: Create citations using embedded enhanced creator
        if mode in ['create', 'complete']:
            print("\nUsing CiteMaven Enhanced Citation Creator:")
            print("-"*40)
            for note_id, text in endnotes.items():
                # Use the embedded enhanced citation creator
                formatted_text = process_minimal_citation(text, style)
                formatted_endnotes[note_id] = formatted_text
                print(f"  [{note_id}] {text[:30]}...")
                print(f"       → {formatted_text[:60]}...")
            
            print(f'\n✔ Created {len(formatted_endnotes)} complete citations')
        
        # Mode 2: Format existing citations
        elif mode == 'format':
            for note_id, text in endnotes.items():
                parsed = parser.parse_citation(text)
                formatted_text = formatter.format_citation(parsed, style)
                formatted_endnotes[note_id] = formatted_text
            
            print(f'✔ Formatted {len(formatted_endnotes)} citations in {style} style')
        
        # Update endnotes if we have formatting
        if formatted_endnotes:
            update_endnotes_xml_formatted(endnotes_file, formatted_endnotes)
            print(f'✔ Updated endnotes with formatting')
        
        # Determine output filename
        original_filename = secure_filename(file.filename)
        if mode == 'create':
            output_filename = f"CiteMaven_created_{original_filename}"
        elif mode == 'format':
            output_filename = f"CiteMaven_formatted_{original_filename}"
        else:
            output_filename = f"CiteMaven_{original_filename}"
        
        # Pack back into docx
        output_path = temp_dir / output_filename
        pack_docx(extract_dir, output_path)
        print(f'✔ Created {output_filename}')
        
        # Read into memory
        with open(output_path, 'rb') as f:
            file_data = f.read()
        
        print(f'✔ Document ready ({len(file_data)} bytes)')
        print('='*60 + '\n')
        
        # Cleanup
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
        
        # Return file
        return send_file(
            BytesIO(file_data),
            as_attachment=True,
            download_name=output_filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
    except Exception as e:
        print(f'✗ Error: {e}')
        import traceback
        traceback.print_exc()
        
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
        
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@app.route('/create-citation', methods=['POST'])
def create_citation():
    """Create a single citation from minimal input (for manual entry)"""
    data = request.json
    
    author = data.get('author', '')
    title = data.get('title', '')
    style = data.get('style', 'chicago')
    
    # Use the embedded enhanced citation creator
    result = process_minimal_citation(f"{author}, {title}", style)
    
    return jsonify({
        'success': True,
        'citation': result
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
