"""
Complete Citation Management System - With Enhanced Citation Creator
Combines: Citation Creator (with fallback database), Citation Formatter, and Incipit Converter
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

# Import the enhanced citation creator
from enhanced_citation_creator import process_minimal_citation

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = 'citation-secret-2024'

parser = CitationParser()
formatter = CitationFormatter()

# Global variables for incipit processing
problem_notes = []

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

# ==================== ENDNOTE EXTRACTION ====================

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

# ==================== FORMATTING WITH STYLES ====================

def update_endnotes_xml_formatted(path, formatted):
    """Update endnotes with formatted citations (Times New Roman 10pt)"""
    dom = minidom.parse(str(path))
    
    for en in dom.getElementsByTagName('w:endnote'):
        en_id = en.getAttribute('w:id')
        
        if en_id in formatted:
            paragraphs = en.getElementsByTagName('w:p')
            if not paragraphs:
                continue
                
            p = paragraphs[0]
            
            # Ensure paragraph has proper style
            pPr_elements = p.getElementsByTagName('w:pPr')
            if not pPr_elements:
                pPr = dom.createElement('w:pPr')
                if p.firstChild:
                    p.insertBefore(pPr, p.firstChild)
                else:
                    p.appendChild(pPr)
            else:
                pPr = pPr_elements[0]
            
            # Ensure EndnoteText style
            pStyle_elements = pPr.getElementsByTagName('w:pStyle')
            if not pStyle_elements:
                pStyle = dom.createElement('w:pStyle')
                pStyle.setAttribute('w:val', 'EndnoteText')
                pPr.appendChild(pStyle)
            
            # Add spacing
            spacing_elements = pPr.getElementsByTagName('w:spacing')
            if not spacing_elements:
                spacing = dom.createElement('w:spacing')
                spacing.setAttribute('w:after', '120')
                pPr.appendChild(spacing)
            
            # Clear text after endnote reference
            found_ref = False
            for child in list(p.childNodes):
                if child.nodeType == child.ELEMENT_NODE:
                    if child.tagName == 'w:r':
                        has_ref = child.getElementsByTagName('w:endnoteRef')
                        if has_ref:
                            found_ref = True
                            # Add space after reference
                            space_run = dom.createElement('w:r')
                            space_text = dom.createElement('w:t')
                            space_text.setAttribute('xml:space', 'preserve')
                            space_text.appendChild(dom.createTextNode(' '))
                            space_run.appendChild(space_text)
                            if child.nextSibling:
                                p.insertBefore(space_run, child.nextSibling)
                            else:
                                p.appendChild(space_run)
                        elif found_ref:
                            try:
                                p.removeChild(child)
                            except:
                                pass
            
            # Add formatted text with Times New Roman 10pt
            formatted_text = formatted[en_id]
            parts = re.split(r'(<em>.*?</em>)', formatted_text)
            
            for part in parts:
                if not part:
                    continue
                    
                new_run = dom.createElement('w:r')
                rPr = dom.createElement('w:rPr')
                
                # Font
                rFonts = dom.createElement('w:rFonts')
                rFonts.setAttribute('w:ascii', 'Times New Roman')
                rFonts.setAttribute('w:hAnsi', 'Times New Roman')
                rPr.appendChild(rFonts)
                
                # Size (20 half-points = 10pt)
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

# ==================== INCIPIT CONVERSION FUNCTIONS ====================

def clean_word_for_output(word):
    """Clean a single word of ALL punctuation"""
    word = re.sub(r'^[^\w]+', '', word)
    word = re.sub(r'[^\w]+$', '', word)
    word = word.strip('.,;:!?"\'\u201C\u201D\u2018\u2019\u00AB\u00BB')
    return word

def is_closing_quote(char):
    return char in ['"', '\u201D', '\'', '\u2019', '\u00BB', '\u203A']

def is_opening_quote(char):
    return char in ['"', '\u201C', '\'', '\u2018', '\u00AB', '\u2039']

def extract_paragraph_text(para):
    """Extract complete text from a paragraph"""
    text_parts = []
    for node in para.childNodes:
        if node.nodeType == node.ELEMENT_NODE:
            if node.tagName == 'w:r':
                if node.getElementsByTagName('w:endnoteReference'):
                    text_parts.append({'type': 'endnote', 'node': node})
                else:
                    run_text = ''
                    for t_elem in node.getElementsByTagName('w:t'):
                        if t_elem.firstChild:
                            run_text += t_elem.firstChild.nodeValue
                    if run_text:
                        text_parts.append({'type': 'text', 'content': run_text})
    return text_parts

def find_context_for_endnote(text_before, endnote_id):
    """Find the appropriate context words for an endnote"""
    global problem_notes
    
    text_before = text_before.strip()
    
    if not text_before:
        problem_notes.append(f"Note {endnote_id}: No text before endnote")
        return "Start of section"
    
    # Check if this ends with a closing quote
    is_quote = False
    check_pos = len(text_before) - 1
    while check_pos >= 0 and text_before[check_pos].isspace():
        check_pos -= 1
    
    if check_pos >= 0 and is_closing_quote(text_before[check_pos]):
        is_quote = True
        quote_depth = 1
        pos = check_pos - 1
        quote_start = 0
        
        while pos >= 0 and quote_depth > 0:
            if is_closing_quote(text_before[pos]):
                quote_depth += 1
            elif is_opening_quote(text_before[pos]):
                quote_depth -= 1
                if quote_depth == 0:
                    quote_start = pos + 1
                    break
            pos -= 1
        
        if quote_start > 0:
            source_text = text_before[quote_start:check_pos].lstrip()
        else:
            source_text = text_before[:check_pos].lstrip()
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
        problem_notes.append(f"Note {endnote_id}: Empty source text")
        return "Beginning of section"
    
    # Split and clean words
    words = source_text.split()
    clean_words = []
    
    for word in words[:20]:
        cleaned = clean_word_for_output(word)
        if cleaned and len(cleaned) > 1:
            clean_words.append(cleaned)
        if len(clean_words) >= 3:
            break
    
    if len(clean_words) >= 3:
        result = ' '.join(clean_words[:3])
    elif len(clean_words) > 0:
        result = ' '.join(clean_words)
    else:
        result = "Beginning of sentence"
    
    return result

def process_endnote_references(doc_path, output_path, endnotes):
    """Replace endnote references with bookmarks and extract context"""
    global problem_notes
    
    with open(doc_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    dom = minidom.parseString(content)
    references = {}
    bookmark_id = 1000
    
    paragraphs = dom.getElementsByTagName('w:p')
    
    for para in paragraphs:
        text_parts = extract_paragraph_text(para)
        accumulated_text = ""
        
        for part in text_parts:
            if part['type'] == 'text':
                accumulated_text += part['content']
            elif part['type'] == 'endnote':
                run = part['node']
                endnote_refs = run.getElementsByTagName('w:endnoteReference')
                
                if endnote_refs:
                    endnote_id = endnote_refs[0].getAttribute('w:id')
                    
                    first_three = find_context_for_endnote(accumulated_text, endnote_id)
                    
                    # Final cleanup
                    words = first_three.split()
                    cleaned_words = []
                    for word in words:
                        cleaned = re.sub(r'[^\w\s]', '', word, flags=re.UNICODE).strip()
                        if cleaned:
                            cleaned_words.append(cleaned)
                    
                    first_three = ' '.join(cleaned_words) if cleaned_words else "Beginning"
                    
                    # Create bookmark
                    bookmark_name = f"endnote_{endnote_id}"
                    references[endnote_id] = {
                        'bookmark': bookmark_name,
                        'first_three': first_three
                    }
                    
                    # Create bookmark elements
                    bookmark_start = dom.createElement('w:bookmarkStart')
                    bookmark_start.setAttribute('w:id', str(bookmark_id))
                    bookmark_start.setAttribute('w:name', bookmark_name)
                    
                    bookmark_end = dom.createElement('w:bookmarkEnd')
                    bookmark_end.setAttribute('w:id', str(bookmark_id))
                    
                    parent = run.parentNode
                    parent.insertBefore(bookmark_start, run)
                    parent.insertBefore(bookmark_end, run)
                    
                    # Remove endnote reference
                    for ref in run.getElementsByTagName('w:endnoteReference'):
                        ref.parentNode.removeChild(ref)
                    
                    if not run.getElementsByTagName('w:t') and not run.childNodes:
                        parent.removeChild(run)
                    
                    bookmark_id += 1
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(dom.toxml())
    
    return references

def create_notes_section_xml(endnotes, references, formatted=None):
    """Create the Notes section with incipit format"""
    notes_xml = []
    
    # Add page break
    notes_xml.append('''  <w:p>
    <w:pPr>
      <w:pageBreakBefore/>
    </w:pPr>
  </w:p>''')
    
    # Add Notes heading
    notes_xml.append('''  <w:p>
    <w:pPr>
      <w:pStyle w:val="Heading1"/>
    </w:pPr>
    <w:r>
      <w:t>Notes</w:t>
    </w:r>
  </w:p>''')
    
    # Add each incipit note
    for note_id in sorted(endnotes.keys(), key=lambda x: int(x)):
        citation = endnotes[note_id]
        
        # If formatted, use the formatted version
        if formatted and note_id in formatted:
            citation = formatted[note_id]
            # Strip HTML tags for plain text in incipit
            citation = re.sub(r'</?em>', '', citation)
        
        # Escape XML characters
        citation = citation.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        
        if note_id in references:
            ref = references[note_id]
            bookmark_name = ref['bookmark']
            first_three = ref['first_three']
            
            first_three = first_three.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            
            note_xml = f'''  <w:p>
    <w:pPr>
      <w:spacing w:after="120"/>
    </w:pPr>
    <w:r>
      <w:fldSimple w:instr=" PAGEREF {bookmark_name} \\h ">
        <w:r>
          <w:t>[Page]</w:t>
        </w:r>
      </w:fldSimple>
    </w:r>
    <w:r>
      <w:t xml:space="preserve"> </w:t>
    </w:r>
    <w:r>
      <w:rPr>
        <w:i/>
        <w:iCs/>
      </w:rPr>
      <w:t>{first_three}:</w:t>
    </w:r>
    <w:r>
      <w:t xml:space="preserve"> {citation}</w:t>
    </w:r>
  </w:p>'''
        else:
            note_xml = f'''  <w:p>
    <w:pPr>
      <w:spacing w:after="120"/>
    </w:pPr>
    <w:r>
      <w:t>[Missing reference] {citation}</w:t>
    </w:r>
  </w:p>'''
        
        notes_xml.append(note_xml)
    
    return '\n'.join(notes_xml)

def add_notes_to_document(doc_path, notes_xml, output_path):
    """Add the notes section to the document"""
    with open(doc_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    body_close_pos = content.rfind('</w:body>')
    
    if body_close_pos == -1:
        return False
    
    sect_pr_pos = content.rfind('<w:sectPr', 0, body_close_pos)
    
    if sect_pr_pos != -1:
        insert_pos = sect_pr_pos
    else:
        insert_pos = body_close_pos
    
    new_content = content[:insert_pos] + notes_xml + '\n' + content[insert_pos:]
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return True

# ==================== WEB INTERFACE ROUTES ====================

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
    
    mode = request.form.get('mode', 'format')  # 'create', 'format', 'incipit', 'complete'
    style = request.form.get('style', 'chicago')
    
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
        
        # Mode 1: Create citations from minimal info using enhanced creator
        if mode in ['create', 'complete']:
            for note_id, text in endnotes.items():
                # Use the enhanced citation creator
                formatted_text = process_minimal_citation(text, style)
                formatted_endnotes[note_id] = formatted_text
                print(f'  [{note_id}] Created: {text[:30]}... → {formatted_text[:50]}...')
            
            print(f'✔ Created {len(formatted_endnotes)} complete citations using enhanced creator')
        
        # Mode 2: Format existing citations (simple preservation with italics)
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
        
        # Convert to incipit if requested
        if mode in ['incipit', 'complete']:
            global problem_notes
            problem_notes = []
            
            doc_file = extract_dir / 'word' / 'document.xml'
            doc_temp = extract_dir / 'word' / 'document_temp.xml'
            
            # Process endnote references and create bookmarks
            references = process_endnote_references(doc_file, doc_temp, endnotes)
            
            # Use formatted citations if available
            notes_to_use = formatted_endnotes if formatted_endnotes else None
            
            # Create notes section
            notes_xml = create_notes_section_xml(endnotes, references, notes_to_use)
            
            # Add notes to document
            success = add_notes_to_document(doc_temp, notes_xml, doc_file)
            if not success:
                return jsonify({'error': 'Failed to add notes section'}), 500
            
            doc_temp.unlink()
            print(f'✔ Created incipit notes section')
        
        # Determine output filename
        original_filename = secure_filename(file.filename)
        if mode == 'create':
            output_filename = f"created_{original_filename}"
        elif mode == 'format':
            output_filename = f"formatted_{original_filename}"
        elif mode == 'incipit':
            output_filename = f"incipit_{original_filename}"
        else:  # complete
            output_filename = f"complete_{original_filename}"
        
        # Pack back into docx
        output_path = temp_dir / output_filename
        pack_docx(extract_dir, output_path)
        print(f'✔ Created {output_filename}')
        
        # Read into memory
        with open(output_path, 'rb') as f:
            file_data = f.read()
        
        print(f'✔ Document ready ({len(file_data)} bytes)')
        
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
    
    # Use the enhanced citation creator
    result = process_minimal_citation(f"{author}, {title}", style)
    
    return jsonify({
        'success': True,
        'citation': result
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
