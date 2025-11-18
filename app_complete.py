"""
CiteMaven - SUPERBULLETPROOF VERSION
Complete self-contained citation management system with robust incipit converter
All functionality embedded - no external module dependencies
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

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = 'citation-secret-2024'

# ==================== EMBEDDED CITATION PARSER ====================
class CitationParser:
    def parse_citation(self, text):
        """Parse a citation text into components"""
        citation = {
            'author': '',
            'title': '',
            'publisher': '',
            'place': '',
            'year': '',
            'page': '',
            'type': 'book'
        }
        
        # Clean text
        text = text.strip()
        
        # Extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        if year_match:
            citation['year'] = year_match.group()
        
        # Extract pages
        page_match = re.search(r'pp?\.\s*(\d+(?:-\d+)?)', text)
        if page_match:
            citation['page'] = page_match.group(1)
        
        # Try to identify author (usually before first comma or period)
        parts = re.split(r'[,.]', text)
        if parts:
            potential_author = parts[0].strip()
            if potential_author and not potential_author.startswith('http'):
                citation['author'] = potential_author
        
        # Try to extract title (often in quotes or italics)
        title_match = re.search(r'"([^"]+)"', text)
        if not title_match:
            title_match = re.search(r'["\']([^"\']+)["\']', text)
        if title_match:
            citation['title'] = title_match.group(1)
        elif len(parts) > 1:
            citation['title'] = parts[1].strip().strip('"\'')
        
        return citation

# ==================== EMBEDDED CITATION FORMATTER ====================
class CitationFormatter:
    def format_citation(self, parsed, style='chicago'):
        """Format parsed citation according to style"""
        if style == 'chicago':
            return self._format_chicago(parsed)
        elif style == 'mla':
            return self._format_mla(parsed)
        elif style == 'apa':
            return self._format_apa(parsed)
        return self._format_chicago(parsed)
    
    def _format_chicago(self, c):
        parts = []
        if c.get('author'):
            parts.append(c['author'])
        if c.get('title'):
            parts.append(f"<em>{c['title']}</em>")
        
        pub_info = []
        if c.get('place'):
            pub_info.append(c['place'])
        if c.get('publisher'):
            pub_info.append(c['publisher'])
        if c.get('year'):
            pub_info.append(c['year'])
        
        if pub_info:
            if c.get('place') and c.get('publisher'):
                parts.append(f"({c['place']}: {c['publisher']}, {c.get('year', '')})")
            else:
                parts.append(f"({', '.join(pub_info)})")
        
        if c.get('page'):
            parts.append(c['page'])
        
        return ', '.join(parts) + '.' if parts else c.get('original_text', '')
    
    def _format_mla(self, c):
        parts = []
        if c.get('author'):
            author_parts = c['author'].split()
            if len(author_parts) >= 2:
                parts.append(f"{author_parts[-1]}, {' '.join(author_parts[:-1])}")
            else:
                parts.append(c['author'])
        if c.get('title'):
            parts.append(f"<em>{c['title']}</em>")
        if c.get('publisher'):
            parts.append(c['publisher'])
        if c.get('year'):
            parts.append(c['year'])
        if c.get('page'):
            parts.append(f"pp. {c['page']}")
        return '. '.join(parts) + '.' if parts else c.get('original_text', '')
    
    def _format_apa(self, c):
        parts = []
        if c.get('author'):
            author_parts = c['author'].split()
            if len(author_parts) >= 2:
                initials = '. '.join([p[0] for p in author_parts[:-1]]) + '.'
                parts.append(f"{author_parts[-1]}, {initials}")
            else:
                parts.append(c['author'])
        if c.get('year'):
            parts.append(f"({c['year']})")
        if c.get('title'):
            parts.append(f"<em>{c['title']}</em>")
        if c.get('place') and c.get('publisher'):
            parts.append(f"{c['place']}: {c['publisher']}")
        elif c.get('publisher'):
            parts.append(c['publisher'])
        return '. '.join(parts) + '.' if parts else c.get('original_text', '')

parser = CitationParser()
formatter = CitationFormatter()

# ==================== EMBEDDED ENHANCED CITATION CREATOR ====================

BOOK_DATABASE = {
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
    'darity from here': {
        'author': 'William A. Darity Jr. and A. Kirsten Mullen',
        'title': 'From Here to Equality: Reparations for Black Americans in the Twenty-First Century',
        'place': 'Chapel Hill',
        'publisher': 'University of North Carolina Press',
        'year': '2020'
    }
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
    'Oxford University Press': 'Oxford',
    'Cambridge University Press': 'Cambridge',
    'Farrar, Straus and Giroux': 'New York',
    'Random House': 'New York',
    'Penguin': 'New York',
    'Norton': 'New York',
    'Knopf': 'New York',
}

def process_minimal_citation(text, style='chicago'):
    """Create complete citation from minimal input"""
    text = text.strip()
    text = re.sub(r'^\s*\d+\s*', '', text)
    
    # Parse
    author_part = ''
    title_part = ''
    
    if ',' in text:
        parts = text.split(',', 1)
        author_part = parts[0].strip()
        title_part = parts[1].strip() if len(parts) > 1 else ''
    else:
        title_part = text
    
    # Search database
    search_key = f"{author_part.lower()} {title_part.lower()}".strip()
    
    book_data = None
    for key, data in BOOK_DATABASE.items():
        if author_part.lower() in key and title_part.lower() in key:
            book_data = data
            break
        elif title_part.lower() in key:
            book_data = data
            break
    
    if book_data:
        citation = f"{book_data['author']}, <em>{book_data['title']}</em>"
        if book_data.get('place') and book_data.get('publisher') and book_data.get('year'):
            citation += f" ({book_data['place']}: {book_data['publisher']}, {book_data['year']})"
        citation += '.'
        return citation
    
    # Fallback
    if author_part and title_part:
        return f"{author_part}, <em>{title_part}</em>."
    return f"<em>{text}</em>."

# ==================== EMBEDDED ROBUST INCIPIT CONVERTER ====================

def extract_endnotes_for_incipit(endnotes_path):
    """Extract endnote content from endnotes.xml for incipit conversion"""
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
            full_text = re.sub(r'^\s*\d*\s*', '', full_text).strip()
            full_text = re.sub(r'^[\s"\':.,;!?\u201C\u201D\u2018\u2019\u00AB\u00BB\u2039\u203A]+', '', full_text)
            
            endnotes[endnote_id] = full_text
    
    return endnotes

def find_context_for_endnote_robust(text_before, endnote_id):
    """Find context words for incipit note"""
    text_before = text_before.strip()
    
    if not text_before:
        return "Start of section"
    
    # Check for closing quote
    check_pos = len(text_before) - 1
    while check_pos >= 0 and text_before[check_pos].isspace():
        check_pos -= 1
    
    is_quote = check_pos >= 0 and text_before[check_pos] in ['"', '\u201D', '\'', '\u2019', '\u00BB', '\u203A']
    
    if is_quote:
        # Find opening quote
        quote_depth = 1
        pos = check_pos - 1
        quote_start = 0
        
        while pos >= 0 and quote_depth > 0:
            if text_before[pos] in ['"', '\u201D', '\'', '\u2019', '\u00BB', '\u203A']:
                quote_depth += 1
            elif text_before[pos] in ['"', '\u201C', '\'', '\u2018', '\u00AB', '\u2039']:
                quote_depth -= 1
                if quote_depth == 0:
                    quote_start = pos + 1
                    break
            pos -= 1
        
        source_text = text_before[quote_start:check_pos].lstrip() if quote_start > 0 else text_before[:check_pos].lstrip()
    else:
        # Find sentence beginning
        sentence_markers = ['. ', '! ', '? ', '.\n', '!\n', '?\n']
        sentence_start = 0
        
        for marker in sentence_markers:
            pos = text_before.rfind(marker)
            if pos > sentence_start:
                sentence_start = pos + len(marker)
        
        source_text = text_before[sentence_start:].lstrip()
    
    if not source_text:
        return "Beginning of section"
    
    # Extract clean words
    words = source_text.split()
    clean_words = []
    
    for word in words[:20]:
        cleaned = re.sub(r'^[^\w]+|[^\w]+$', '', word).strip('.,;:!?"\'\u201C\u201D\u2018\u2019\u00AB\u00BB')
        if cleaned and len(cleaned) > 1:
            clean_words.append(cleaned)
        if len(clean_words) >= 3:
            break
    
    if len(clean_words) >= 3:
        return ' '.join(clean_words[:3])
    elif len(clean_words) > 0:
        return ' '.join(clean_words)
    else:
        return "Beginning of sentence"

def convert_document_robust(input_docx, output_docx=None):
    """Robust incipit conversion function"""
    input_path = Path(input_docx)
    if not input_path.exists():
        return False
    
    if output_docx is None:
        output_docx = input_path.stem + '_incipit.docx'
    
    output_path = Path(output_docx)
    
    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        # Unpack document
        with zipfile.ZipFile(input_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Check for endnotes
        endnotes_file = temp_dir / 'word' / 'endnotes.xml'
        if not endnotes_file.exists():
            return False
        
        # Extract endnotes
        endnotes = extract_endnotes_for_incipit(endnotes_file)
        
        # Process document for incipit references
        doc_file = temp_dir / 'word' / 'document.xml'
        
        with open(doc_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        dom = minidom.parseString(content)
        references = {}
        bookmark_id = 1000
        
        # Process paragraphs to find endnote references
        for para in dom.getElementsByTagName('w:p'):
            accumulated_text = ""
            
            for node in para.childNodes:
                if node.nodeType == node.ELEMENT_NODE and node.tagName == 'w:r':
                    # Check for endnote reference
                    endnote_refs = node.getElementsByTagName('w:endnoteReference')
                    if endnote_refs:
                        endnote_id = endnote_refs[0].getAttribute('w:id')
                        
                        # Get context
                        first_three = find_context_for_endnote_robust(accumulated_text, endnote_id)
                        
                        # Create bookmark
                        bookmark_name = f"endnote_{endnote_id}"
                        references[endnote_id] = {
                            'bookmark': bookmark_name,
                            'first_three': first_three
                        }
                        
                        # Add bookmark elements
                        bookmark_start = dom.createElement('w:bookmarkStart')
                        bookmark_start.setAttribute('w:id', str(bookmark_id))
                        bookmark_start.setAttribute('w:name', bookmark_name)
                        
                        bookmark_end = dom.createElement('w:bookmarkEnd')
                        bookmark_end.setAttribute('w:id', str(bookmark_id))
                        
                        parent = node.parentNode
                        parent.insertBefore(bookmark_start, node)
                        parent.insertBefore(bookmark_end, node)
                        
                        # Remove endnote reference
                        for ref in node.getElementsByTagName('w:endnoteReference'):
                            ref.parentNode.removeChild(ref)
                        
                        bookmark_id += 1
                    else:
                        # Accumulate text
                        for t_elem in node.getElementsByTagName('w:t'):
                            if t_elem.firstChild:
                                accumulated_text += t_elem.firstChild.nodeValue
        
        # Create notes section
        notes_xml = []
        notes_xml.append('<w:p><w:pPr><w:pageBreakBefore/></w:pPr></w:p>')
        notes_xml.append('<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Notes</w:t></w:r></w:p>')
        
        for note_id in sorted(endnotes.keys(), key=lambda x: int(x)):
            citation = endnotes[note_id]
            citation = citation.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            
            if note_id in references:
                ref = references[note_id]
                bookmark_name = ref['bookmark']
                first_three = ref['first_three'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                
                note_xml = f'''<w:p>
<w:pPr><w:spacing w:after="120"/></w:pPr>
<w:r><w:fldSimple w:instr=" PAGEREF {bookmark_name} \\h "><w:r><w:t>[Page]</w:t></w:r></w:fldSimple></w:r>
<w:r><w:t xml:space="preserve"> </w:t></w:r>
<w:r><w:rPr><w:i/><w:iCs/></w:rPr><w:t>{first_three}:</w:t></w:r>
<w:r><w:t xml:space="preserve"> {citation}</w:t></w:r>
</w:p>'''
                notes_xml.append(note_xml)
        
        # Add notes to document
        notes_content = '\n'.join(notes_xml)
        body_close_pos = content.rfind('</w:body>')
        if body_close_pos == -1:
            return False
        
        new_content = content[:body_close_pos] + notes_content + '\n' + content[body_close_pos:]
        
        with open(doc_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        # Pack document
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)
        
        return True
        
    except Exception as e:
        print(f"Error during conversion: {e}")
        return False
        
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

# ==================== DOCX PROCESSING FUNCTIONS ====================

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
            text = re.sub(r'^\s*\d*\s*', '', text).strip()
            endnotes[en_id] = text
    return endnotes

def update_endnotes_xml_formatted(path, formatted):
    """Update endnotes with formatted citations"""
    dom = minidom.parse(str(path))
    
    for en in dom.getElementsByTagName('w:endnote'):
        en_id = en.getAttribute('w:id')
        
        if en_id in formatted:
            paragraphs = en.getElementsByTagName('w:p')
            if not paragraphs:
                continue
                
            p = paragraphs[0]
            
            # Clear and rebuild with formatting
            for pPr in p.getElementsByTagName('w:pPr'):
                p.removeChild(pPr)
            
            pPr = dom.createElement('w:pPr')
            pStyle = dom.createElement('w:pStyle')
            pStyle.setAttribute('w:val', 'EndnoteText')
            pPr.appendChild(pStyle)
            spacing = dom.createElement('w:spacing')
            spacing.setAttribute('w:after', '120')
            pPr.appendChild(spacing)
            
            if p.firstChild:
                p.insertBefore(pPr, p.firstChild)
            else:
                p.appendChild(pPr)
            
            # Find endnoteRef
            endnote_ref_run = None
            for run in p.getElementsByTagName('w:r'):
                if run.getElementsByTagName('w:endnoteRef'):
                    endnote_ref_run = run
                    break
            
            # Remove all other runs
            for run in list(p.getElementsByTagName('w:r')):
                if run != endnote_ref_run:
                    try:
                        p.removeChild(run)
                    except:
                        pass
            
            # Add formatted text
            formatted_text = formatted[en_id]
            parts = re.split(r'(<em>.*?</em>)', formatted_text)
            
            for part in parts:
                if not part:
                    continue
                
                new_run = dom.createElement('w:r')
                rPr = dom.createElement('w:rPr')
                
                # Times New Roman, 10pt
                rFonts = dom.createElement('w:rFonts')
                rFonts.setAttribute('w:ascii', 'Times New Roman')
                rFonts.setAttribute('w:hAnsi', 'Times New Roman')
                rPr.appendChild(rFonts)
                
                sz = dom.createElement('w:sz')
                sz.setAttribute('w:val', '20')
                rPr.appendChild(sz)
                
                # Handle italics
                if '<em>' in part:
                    i_elem = dom.createElement('w:i')
                    rPr.appendChild(i_elem)
                    part = re.sub(r'</?em>', '', part)
                
                new_run.appendChild(rPr)
                
                new_text = dom.createElement('w:t')
                new_text.setAttribute('xml:space', 'preserve')
                new_text.appendChild(dom.createTextNode(part))
                new_run.appendChild(new_text)
                
                p.appendChild(new_run)
    
    with open(str(path), 'wb') as f:
        f.write(dom.toxml(encoding='UTF-8'))

# ==================== FLASK ROUTES ====================

@app.route('/')
def index():
    return render_template('index_complete.html')

@app.route('/process', methods=['POST'])
def process():
    """Main processing route for CiteMaven"""
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if not file.filename or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file. Please upload a .docx file'}), 400
    
    mode = request.form.get('mode', 'format')
    style = request.form.get('style', 'chicago')
    
    print(f"\nCiteMaven Processing: {file.filename}")
    print(f"Mode: {mode}, Style: {style}")
    
    # Special handling for robust incipit mode
    if mode == 'robust-incipit':
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, secure_filename(file.filename))
            output_path = os.path.join(tmpdir, f'CiteMaven_robust_incipit_{file.filename}')
            
            file.save(input_path)
            success = convert_document_robust(input_path, output_path)
            
            if success and os.path.exists(output_path):
                return send_file(
                    output_path,
                    as_attachment=True,
                    download_name=f"CiteMaven_robust_incipit_{file.filename}",
                    mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
            else:
                return jsonify({'error': 'Robust incipit conversion failed'}), 500
    
    # Regular processing for other modes
    temp_dir = None
    
    try:
        temp_dir = Path(tempfile.mkdtemp())
        input_path = temp_dir / 'input.docx'
        file.save(input_path)
        
        extract_dir = temp_dir / 'extracted'
        unpack_docx(input_path, extract_dir)
        
        endnotes_file = extract_dir / 'word' / 'endnotes.xml'
        if not endnotes_file.exists():
            return jsonify({'error': 'No endnotes found in document'}), 400
        
        endnotes = extract_endnotes(endnotes_file)
        print(f'✔ Extracted {len(endnotes)} endnotes')
        
        formatted_endnotes = {}
        
        # Mode: Create citations
        if mode == 'create':
            print("Using CiteMaven Smart Citation Creation")
            for note_id, text in endnotes.items():
                formatted_text = process_minimal_citation(text, style)
                formatted_endnotes[note_id] = formatted_text
            print(f'✔ Created {len(formatted_endnotes)} complete citations')
        
        # Mode: Format existing citations
        elif mode == 'format':
            for note_id, text in endnotes.items():
                parsed = parser.parse_citation(text)
                formatted_text = formatter.format_citation(parsed, style)
                formatted_endnotes[note_id] = formatted_text
            print(f'✔ Formatted {len(formatted_endnotes)} citations')
        
        # Update endnotes if needed
        if formatted_endnotes:
            update_endnotes_xml_formatted(endnotes_file, formatted_endnotes)
            print('✔ Updated endnotes with formatting')
        
        # Determine output filename
        original_filename = secure_filename(file.filename)
        if mode == 'create':
            output_filename = f"CiteMaven_created_{original_filename}"
        elif mode == 'format':
            output_filename = f"CiteMaven_formatted_{original_filename}"
        else:
            output_filename = f"CiteMaven_{original_filename}"
        
        # Pack and return
        output_path = temp_dir / output_filename
        pack_docx(extract_dir, output_path)
        
        with open(output_path, 'rb') as f:
            file_data = f.read()
        
        print(f'✔ Document ready ({len(file_data)} bytes)')
        
        # Cleanup
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
        
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
    """Create single citation from manual input"""
    data = request.json
    
    author = data.get('author', '')
    title = data.get('title', '')
    style = data.get('style', 'chicago')
    
    result = process_minimal_citation(f"{author}, {title}", style)
    
    return jsonify({
        'success': True,
        'citation': result
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
