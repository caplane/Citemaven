"""
Citation Processor - FIXED VERSION
"""
from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for
from werkzeug.utils import secure_filename
from io import BytesIO
import os, zipfile, xml.dom.minidom as minidom, re, requests
from pathlib import Path
import shutil, tempfile, uuid
from citation_parser import CitationParser
from citation_formatter import CitationFormatter

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = 'citation-secret-2024'

parser = CitationParser()
formatter = CitationFormatter()
session_storage = {}  # FIX: Server-side storage

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'docx'

def unpack_docx(docx_path, extract_dir):
    with zipfile.ZipFile(docx_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

def pack_docx(source_dir, output_path):
    if os.path.exists(output_path): os.remove(output_path)
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), source_dir))

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
    """Update endnotes.xml with formatted citations - preserving formatting"""
    dom = minidom.parse(str(path))
    
    for en in dom.getElementsByTagName('w:endnote'):
        en_id = en.getAttribute('w:id')
        if en_id in formatted:
            texts = en.getElementsByTagName('w:t')
            if texts and texts[0].firstChild:
                # Strip HTML tags
                text = formatted[en_id]
                text = re.sub(r'<em>|</em>', '', text)
                texts[0].firstChild.nodeValue = text
    
    # Write back preserving structure
    with open(str(path), 'wb') as f:
        f.write(dom.toxml(encoding='UTF-8'))
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    if not file.filename or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file'}), 400
    
    session_id = str(uuid.uuid4())
    temp_dir = Path(tempfile.mkdtemp())
    input_path = temp_dir / 'input.docx'
    file.save(input_path)
    
    try:
        extract_dir = temp_dir / 'extracted'
        unpack_docx(input_path, extract_dir)
        endnotes_file = extract_dir / 'word' / 'endnotes.xml'
        if not endnotes_file.exists():
            shutil.rmtree(temp_dir)
            return jsonify({'error': 'No endnotes found'}), 400
        
        endnotes = extract_endnotes(endnotes_file)
        print(f'DEBUG: Extracted {len(endnotes)} endnotes')
        style = request.form.get('style', 'chicago')
        processed = []
        
        for note_id, text in endnotes.items():
            parsed = parser.parse_citation(text)
            formatted_text = formatter.format_citation(parsed, style)
            processed.append({
                'id': note_id,
                'original_text': text,
                'source_type': parsed['source_type'],
                'confidence': parsed.get('confidence', 'medium'),
                'formatted_text': formatted_text,
                'style': style
            })
        
        print(f"DEBUG: About to store {len(processed)} citations")
        session_storage[session_id] = {
            'citations': processed,
            'citation_style': style,
            'original_filename': secure_filename(file.filename),
            'temp_dir': str(temp_dir)
        }
        
        return redirect(url_for('review', sid=session_id))
    except Exception as e:
        if temp_dir.exists(): shutil.rmtree(temp_dir)
        return jsonify({'error': str(e)}), 500

@app.route('/review')
def review():
    print('DEBUG: Review route called')
    sid = request.args.get('sid')
    print(f"DEBUG: Session ID from URL: {sid}")
    print(f"DEBUG: Session storage keys: {list(session_storage.keys())}")
    if not sid or sid not in session_storage:
        return redirect(url_for('index'))
    data = session_storage[sid]
    print(f"DEBUG: Data keys: {data.keys()}")
    print(f"DEBUG: Number of citations in data: {len(data.get("citations", []))}")
    return render_template('review.html', 
                         citations=data['citations'],
                         style=data['citation_style'],
                         session_id=sid)

@app.route('/finalize', methods=['POST'])
def finalize():
    try:
        data = request.get_json()
        edited = data.get('edited', {})
        sid = data.get('session_id')
        
        if not sid or sid not in session_storage:
            return jsonify({'error': 'Session expired'}), 400
        
    print(f"DEBUG: Number of citations in data: {len(data.get("citations", []))}")
        
        formatted_endnotes = {}
        for i, cit in enumerate(sdata['citations']):
            formatted_endnotes[cit['id']] = edited.get(str(i), cit['formatted_text'])
        
        extract_dir = temp_dir / 'extracted'
        update_endnotes_xml(extract_dir / 'word' / 'endnotes.xml', formatted_endnotes)
        
        output_path = temp_dir / f"formatted_{sdata['original_filename']}"
        pack_docx(extract_dir, output_path)
        
        # FIX: Read into memory before cleanup
        with open(output_path, 'rb') as f:
            file_data = f.read()
        
        try:
            shutil.rmtree(temp_dir)
            del session_storage[sid]
        except: pass
        
        return send_file(BytesIO(file_data), as_attachment=True,
                        download_name=f"formatted_{sdata['original_filename']}",
                        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
