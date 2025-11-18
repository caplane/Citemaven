"""
Citation Processor Web Application
Transforms Word documents with incomplete endnotes into properly formatted citations
Combines incipit note creation with intelligent citation lookup
"""

from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import os
import zipfile
import xml.dom.minidom as minidom
import re
import requests
from pathlib import Path
import shutil
import tempfile
from datetime import datetime

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

ALLOWED_EXTENSIONS = {'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==================== CITATION FORMATTING ====================

PUBLISHER_PLACE_MAP = {
    # US University Presses
    'Harvard University Press': 'Cambridge',
    'MIT Press': 'Cambridge',
    'Yale University Press': 'New Haven',
    'Princeton University Press': 'Princeton',
    'Stanford University Press': 'Stanford',
    'University of California Press': 'Berkeley',
    'University of Chicago Press': 'Chicago',
    'Columbia University Press': 'New York',
    'Cornell University Press': 'Ithaca',
    'Duke University Press': 'Durham',
    'Johns Hopkins University Press': 'Baltimore',
    # Add more as needed - using subset for now
    'Oxford University Press': 'Oxford',
    'Cambridge University Press': 'Cambridge',
    'Penguin': 'New York',
    'Random House': 'New York',
    'HarperCollins': 'New York',
    'Simon & Schuster': 'New York',
}

def infer_place_from_publisher(publisher):
    """Infer publication place from publisher name"""
    if not publisher:
        return ''
    
    for pub, place in PUBLISHER_PLACE_MAP.items():
        if pub.lower() in publisher.lower() or publisher.lower() in pub.lower():
            return place
    return ''

def format_chicago(citation_data):
    """Format citation in Chicago style"""
    author = citation_data.get('author', '') or ''
    title = citation_data.get('title', '') or ''
    place = citation_data.get('place', '') or ''
    publisher = citation_data.get('publisher', '') or ''
    year = citation_data.get('year', '') or ''
    page = citation_data.get('page', '') or ''
    
    citation = f"{author}, <em>{title}</em>"
    
    if place or publisher or year:
        citation += ' ('
        if place:
            citation += place
            if publisher or year:
                citation += ': '
        if publisher:
            citation += publisher
            if year:
                citation += ', '
        if year:
            citation += str(year)
        citation += ')'
    
    if page:
        citation += f', {page}'
    citation += '.'
    
    return citation

def format_mla(citation_data):
    """Format citation in MLA style"""
    author = citation_data.get('author', '') or ''
    title = citation_data.get('title', '') or ''
    publisher = citation_data.get('publisher', '') or ''
    year = citation_data.get('year', '') or ''
    page = citation_data.get('page', '') or ''
    
    # MLA inverts first author's name
    if author:
        author_parts = author.split(' ')
        if len(author_parts) >= 2:
            author = f"{author_parts[-1]}, {' '.join(author_parts[:-1])}"
    
    citation = f"{author}. <em>{title}</em>"
    if publisher:
        citation += f". {publisher}"
    if year:
        citation += f", {year}"
    if page:
        citation += f", pp. {page}"
    citation += '.'
    
    return citation

def format_apa(citation_data):
    """Format citation in APA style"""
    author = citation_data.get('author', '') or ''
    title = citation_data.get('title', '') or ''
    place = citation_data.get('place', '') or ''
    publisher = citation_data.get('publisher', '') or ''
    year = citation_data.get('year', '') or ''
    page = citation_data.get('page', '') or ''
    
    # APA uses initials
    if author:
        author_parts = author.split(' ')
        if len(author_parts) >= 2:
            initials = '. '.join([p[0] for p in author_parts[:-1]]) + '.'
            author = f"{author_parts[-1]}, {initials}"
    
    citation = author
    if year:
        citation += f" ({year})."
    citation += f" <em>{title}</em>"
    
    if place and publisher:
        citation += f". {place}: {publisher}"
    elif publisher:
        citation += f". {publisher}"
    
    if page:
        citation += f", pp. {page}"
    citation += '.'
    
    return citation

def format_bluebook(citation_data):
    """Format citation in Bluebook style"""
    author = citation_data.get('author', '') or ''
    title = citation_data.get('title', '') or ''
    publisher = citation_data.get('publisher', '') or ''
    year = citation_data.get('year', '') or ''
    page = citation_data.get('page', '') or ''
    
    citation = f"{author}, " if author else ''
    citation += title.upper() if title else 'UNTITLED'
    
    if page:
        citation += f" {page}"
    
    if publisher or year:
        citation += ' ('
        if publisher:
            citation += publisher
        if publisher and year:
            citation += ' '
        if year:
            citation += str(year)
        citation += ')'
    
    citation += '.'
    return citation

def format_citation(citation_data, style):
    """Format citation according to specified style"""
    if style == 'chicago':
        return format_chicago(citation_data)
    elif style == 'mla':
        return format_mla(citation_data)
    elif style == 'apa':
        return format_apa(citation_data)
    elif style == 'bluebook':
        return format_bluebook(citation_data)
    else:
        return format_chicago(citation_data)  # Default to Chicago

# ==================== CITATION LOOKUP ====================

def lookup_citation(author=None, title=None):
    """Look up complete citation data from Open Library"""
    if not (author or title):
        return None
    
    query = f"{author or ''} {title or ''}".strip()
    
    try:
        response = requests.get(
            'https://openlibrary.org/search.json',
            params={'q': query, 'limit': 1},
            timeout=5
        )
        
        if response.ok:
            data = response.json()
            if data.get('docs') and len(data['docs']) > 0:
                doc = data['docs'][0]
                
                citation_data = {
                    'author': doc.get('author_name', [None])[0] if doc.get('author_name') else author,
                    'title': doc.get('title', title),
                    'publisher': doc.get('publisher', [None])[0] if doc.get('publisher') else None,
                    'place': doc.get('publish_place', [None])[0] if doc.get('publish_place') else None,
                    'year': doc.get('first_publish_year', None)
                }
                
                # Try to infer place if missing
                if not citation_data['place'] and citation_data['publisher']:
                    citation_data['place'] = infer_place_from_publisher(citation_data['publisher'])
                
                return citation_data
    except Exception as e:
        print(f"Error looking up citation: {e}")
    
    return None

def parse_endnote_text(text):
    """Parse endnote text to extract citation components"""
    # Remove leading numbers and spaces
    text = re.sub(r'^\s*\d+\s*', '', text).strip()
    
    citation_data = {
        'author': None,
        'title': None,
        'publisher': None,
        'place': None,
        'year': None,
        'page': None,
        'original_text': text
    }
    
    # Try to extract year
    year_match = re.search(r'\b(19|20)\d{2}\b', text)
    if year_match:
        citation_data['year'] = year_match.group()
    
    # Try to extract page numbers
    page_match = re.search(r'\b(\d+(?:-\d+)?)\s*\.?\s*$', text)
    if page_match:
        citation_data['page'] = page_match.group(1)
    
    # Simple heuristic: first capitalized phrase before comma is likely author
    parts = text.split(',')
    if len(parts) >= 2:
        potential_author = parts[0].strip()
        if potential_author and potential_author[0].isupper():
            citation_data['author'] = potential_author
        
        # Second part might be title
        potential_title = parts[1].strip()
        # Remove common quote marks
        potential_title = re.sub(r'^["\'\u201C\u201D\u2018\u2019]+|["\'\u201C\u201D\u2018\u2019]+$', '', potential_title)
        if potential_title:
            citation_data['title'] = potential_title
    
    return citation_data

# ==================== DOCX PROCESSING ====================

def unpack_docx(docx_path, extract_dir):
    """Extract a .docx file to a directory"""
    with zipfile.ZipFile(docx_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

def pack_docx(source_dir, output_path):
    """Pack a directory back into a .docx file"""
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, arcname)

def extract_endnotes(endnotes_path):
    """Extract endnote content from endnotes.xml"""
    with open(endnotes_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    dom = minidom.parseString(content)
    endnotes = {}
    
    for endnote in dom.getElementsByTagName('w:endnote'):
        endnote_id = endnote.getAttribute('w:id')
        if endnote_id and endnote_id not in ['-1', '0']:
            text_elements = []
            for t_elem in endnote.getElementsByTagName('w:t'):
                text_elements.append(t_elem.firstChild.nodeValue if t_elem.firstChild else '')
            
            full_text = ''.join(text_elements)
            endnotes[endnote_id] = full_text
    
    return endnotes

def update_endnotes_xml(endnotes_path, formatted_endnotes):
    """Update endnotes.xml with formatted citations"""
    with open(endnotes_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    dom = minidom.parseString(content)
    
    for endnote in dom.getElementsByTagName('w:endnote'):
        endnote_id = endnote.getAttribute('w:id')
        
        if endnote_id in formatted_endnotes:
            # Clear existing text
            for t_elem in endnote.getElementsByTagName('w:t'):
                if t_elem.firstChild:
                    t_elem.firstChild.nodeValue = ''
            
            # Find or create the first w:t element
            t_elements = endnote.getElementsByTagName('w:t')
            if t_elements:
                t_elem = t_elements[0]
                # Create text node with formatted citation
                formatted_text = formatted_endnotes[endnote_id]
                # Remove HTML tags for XML
                formatted_text = re.sub(r'<em>|</em>', '', formatted_text)
                t_elem.firstChild.nodeValue = formatted_text
    
    # Write back
    with open(endnotes_path, 'w', encoding='utf-8') as f:
        f.write(dom.toxml())

def process_document(input_path, output_path, citation_style='chicago', use_incipit=False):
    """Process a Word document to format citations"""
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        # Unpack document
        unpack_docx(input_path, temp_dir)
        
        # Check for endnotes
        endnotes_file = temp_dir / 'word' / 'endnotes.xml'
        if not endnotes_file.exists():
            return {'success': False, 'error': 'No endnotes found in document'}
        
        # Extract endnotes
        endnotes = extract_endnotes(endnotes_file)
        
        # Process each endnote
        formatted_endnotes = {}
        processing_log = []
        
        for note_id, note_text in endnotes.items():
            # Parse existing citation
            parsed = parse_endnote_text(note_text)
            
            # Try to look up complete data if we have author or title
            if parsed['author'] or parsed['title']:
                lookup_result = lookup_citation(parsed['author'], parsed['title'])
                if lookup_result:
                    # Merge parsed data with lookup results
                    for key, value in lookup_result.items():
                        if value and not parsed.get(key):
                            parsed[key] = value
            
            # Format according to chosen style
            formatted = format_citation(parsed, citation_style)
            formatted_endnotes[note_id] = formatted
            
            processing_log.append({
                'id': note_id,
                'original': note_text[:100],
                'formatted': formatted[:100]
            })
        
        # Update endnotes.xml
        update_endnotes_xml(endnotes_file, formatted_endnotes)
        
        # Pack document
        pack_docx(temp_dir, output_path)
        
        return {
            'success': True,
            'endnotes_processed': len(formatted_endnotes),
            'log': processing_log
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}
    
    finally:
        # Cleanup
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    # Check if file was uploaded
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Only .docx files are supported'}), 400
    
    # Get parameters
    citation_style = request.form.get('style', 'chicago')
    use_incipit = request.form.get('format') == 'incipit'
    
    # Save uploaded file
    filename = secure_filename(file.filename)
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(input_path)
    
    # Generate output filename
    base_name = Path(filename).stem
    output_filename = f"{base_name}_formatted.docx"
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
    
    try:
        # Process document
        result = process_document(input_path, output_path, citation_style, use_incipit)
        
        if result['success']:
            return send_file(
                output_path,
                as_attachment=True,
                download_name=output_filename,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
        else:
            return jsonify({'error': result.get('error', 'Processing failed')}), 500
    
    finally:
        # Cleanup uploaded file
        if os.path.exists(input_path):
            os.remove(input_path)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
