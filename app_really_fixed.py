"""
Citation Processor - Fixed DOM Manipulation
"""
from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
from io import BytesIO
import os
import zipfile
import xml.dom.minidom as minidom
import re
from pathlib import Path
import shutil
import tempfile

from citation_parser import CitationParser
from citation_formatter import CitationFormatter

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = 'citation-secret-2024'

parser = CitationParser()
formatter = CitationFormatter()

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
    dom = minidom.parse(str(path))
    endnotes = {}
    for en in dom.getElementsByTagName('w:endnote'):
        en_id = en.getAttribute('w:id')
        if en_id and en_id not in ['-1', '0']:
            text = ''.join([t.firstChild.nodeValue for t in en.getElementsByTagName('w:t') if t.firstChild])
            endnotes[en_id] = text
    return endnotes

def update_endnotes_xml(path, formatted):
    """
    FIXED: Properly handles complex DOM structure without errors
    """
    dom = minidom.parse(str(path))
    
    for en in dom.getElementsByTagName('w:endnote'):
        en_id = en.getAttribute('w:id')
        
        if en_id in formatted:
            # Get the paragraph element
            paragraphs = en.getElementsByTagName('w:p')
            if not paragraphs:
                continue
                
            p = paragraphs[0]
            
            # Clear all text content AFTER the endnote reference
            found_ref = False
            for child in list(p.childNodes):  # Work on a copy
                if child.nodeType == child.ELEMENT_NODE:
                    if child.tagName == 'w:r':
                        # Check if this run has the endnote reference
                        has_ref = child.getElementsByTagName('w:endnoteRef')
                        if has_ref:
                            found_ref = True
                        elif found_ref:
                            # This run comes after the reference - remove it
                            try:
                                p.removeChild(child)
                            except:
                                pass
            
            # Add the new formatted text
            new_run = dom.createElement('w:r')
            new_text = dom.createElement('w:t')
            new_text.setAttribute('xml:space', 'preserve')
            
            # Strip HTML tags
            clean_text = re.sub(r'<em>|</em>', '', formatted[en_id])
            
            # Add text content
            text_content = dom.createTextNode(clean_text)
            new_text.appendChild(text_content)
            new_run.appendChild(new_text)
            
            # Append to paragraph
            p.appendChild(new_run)
    
    # Write back
    with open(str(path), 'wb') as f:
        f.write(dom.toxml(encoding='UTF-8'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    """One-step processing: upload → format → download"""
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if not file.filename or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file. Please upload a .docx file'}), 400
    
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
        print(f'✓ Extracted {len(endnotes)} endnotes')
        
        if len(endnotes) == 0:
            return jsonify({'error': 'No endnotes found in document'}), 400
        
        # Get citation style
        style = request.form.get('style', 'chicago')
        
        # Process each endnote
        formatted_endnotes = {}
        for note_id, text in endnotes.items():
            # Parse citation
            parsed = parser.parse_citation(text)
            
            # Format according to style
            formatted_text = formatter.format_citation(parsed, style)
            
            # Store formatted version
            formatted_endnotes[note_id] = formatted_text
            
            print(f'  [{note_id}] {parsed["source_type"]}: {text[:50]}...')
        
        print(f'✓ Formatted {len(formatted_endnotes)} citations in {style} style')
        
        # Update endnotes.xml (FIXED!)
        update_endnotes_xml(endnotes_file, formatted_endnotes)
        print(f'✓ Updated endnotes.xml successfully')
        
        # Pack back into docx
        original_filename = secure_filename(file.filename)
        output_filename = f"formatted_{original_filename}"
        output_path = temp_dir / output_filename
        pack_docx(extract_dir, output_path)
        print(f'✓ Created {output_filename}')
        
        # Read into memory before cleanup
        with open(output_path, 'rb') as f:
            file_data = f.read()
        
        print(f'✓ Document ready ({len(file_data)} bytes)')
        
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
        
        # Cleanup on error
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
        
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
