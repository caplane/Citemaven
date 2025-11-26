import os
import zipfile
import shutil
import tempfile
import re
from flask import Flask, render_template, request, jsonify, send_file, session
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'incipit-genie-production-key'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# Directory settings
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'docx'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==========================================
#  CORE INCIPIT LOGIC
# ==========================================

def transform_to_incipit(original_text, word_limit=5):
    """
    Transforms citation to incipit based on word count.
    """
    # 1. Clean extra spaces
    cleaned = ' '.join(original_text.split())
    
    # 2. Split logic
    # If text has a parenthesis (City: Publisher), usually the title is before it.
    if '(' in cleaned:
        pre_paren = cleaned.split('(')[0].strip()
        words = pre_paren.split()
        if len(words) > word_limit:
            return ' '.join(words[:word_limit]) + "..."
        return pre_paren
    
    # 3. Fallback word count
    words = cleaned.split()
    if len(words) > word_limit:
        return ' '.join(words[:word_limit]) + "..."
        
    return cleaned

# ==========================================
#  DOCX PROCESSING PIPELINE
# ==========================================

def extract_docx_xml(file_path):
    temp_dir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        endnotes_path = os.path.join(temp_dir, 'word', 'endnotes.xml')
        endnotes_content = ""
        
        if os.path.exists(endnotes_path):
            with open(endnotes_path, 'r', encoding='utf-8') as f:
                endnotes_content = f.read()
        
        return {
            'endnotes': endnotes_content,
            'temp_dir': temp_dir
        }
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise e

def parse_endnotes_text(xml_content):
    if not xml_content:
        return []
        
    citations = []
    # Find all endnotes
    note_pattern = r'<w:endnote[^>]*w:id="(\d+)"[^>]*>(.*?)</w:endnote>'
    matches = re.finditer(note_pattern, xml_content, re.DOTALL)
    
    for match in matches:
        note_id = match.group(1)
        note_content = match.group(2)
        
        if note_id in ['-1', '0']: 
            continue
            
        text_pattern = r'<w:t[^>]*>([^<]+)</w:t>'
        texts = re.findall(text_pattern, note_content)
        full_text = ''.join(texts)
        
        if full_text.strip():
            citations.append({
                'id': note_id,
                'text': full_text.strip()
            })
            
    return citations

def rebuild_docx_with_incipits(original_structure, formatted_map, output_path, style_pref='none'):
    """
    Replaces citation text and applies formatting (Bold/Italic).
    """
    temp_dir = original_structure['temp_dir']
    endnotes_path = os.path.join(temp_dir, 'word', 'endnotes.xml')
    
    with open(endnotes_path, 'r', encoding='utf-8') as f:
        xml_content = f.read()
    
    # Define style XML tags
    # <w:rPr> is Run Properties
    # <w:b/> is Bold, <w:i/> is Italic
    style_xml = ""
    if style_pref in ['bold', 'bold_italic']:
        style_xml += "<w:b/>"
    if style_pref in ['italic', 'bold_italic']:
        style_xml += "<w:i/>"
        
    for note_id, new_text in formatted_map.items():
        # Find the specific endnote block
        note_pattern = f'(<w:endnote[^>]*w:id="{note_id}"[^>]*>)(.*?)(</w:endnote>)'
        match = re.search(note_pattern, xml_content, re.DOTALL)
        
        if match:
            start_tag = match.group(1)
            end_tag = match.group(3)
            
            # Construct new content
            new_inner_xml = (
                f'<w:p>'
                f'<w:pPr><w:pStyle w:val="EndnoteText"/></w:pPr>'
                f'<w:r>'
                f'<w:rPr>{style_xml}</w:rPr>'
                f'<w:t xml:space="preserve">{new_text}</w:t>'
                f'</w:r>'
                f'</w:p>'
            )
            
            full_replacement = f"{start_tag}{new_inner_xml}{end_tag}"
            xml_content = xml_content.replace(match.group(0), full_replacement)

    with open(endnotes_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)
        
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, temp_dir)
                zipf.write(file_path, arcname)

# ==========================================
#  ROUTES
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        save_path = os.path.join(UPLOAD_FOLDER, f"{timestamp}_{filename}")
        file.save(save_path)
        
        try:
            structure = extract_docx_xml(save_path)
            citations = parse_endnotes_text(structure['endnotes'])
            
            session['current_file'] = save_path
            session['original_filename'] = filename
            
            shutil.rmtree(structure['temp_dir'], ignore_errors=True)
            
            return jsonify({
                'success': True,
                'count': len(citations)
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
            
    return jsonify({'error': 'Invalid file'}), 400

@app.route('/transform', methods=['POST'])
def transform():
    if 'current_file' not in session:
        return jsonify({'error': 'No file uploaded'}), 400
    
    data = request.json
    word_count = data.get('word_count', 5)
    style_pref = data.get('style', 'none')
    
    file_path = session['current_file']
    
    try:
        structure = extract_docx_xml(file_path)
        citations = parse_endnotes_text(structure['endnotes'])
        
        formatted_map = {}
        for citation in citations:
            new_text = transform_to_incipit(citation['text'], word_limit=word_count)
            formatted_map[citation['id']] = new_text
            
        output_filename = f"Incipit_{style_pref}_{session['original_filename']}"
        output_path = os.path.join(UPLOAD_FOLDER, output_filename)
        
        rebuild_docx_with_incipits(structure, formatted_map, output_path, style_pref=style_pref)
        
        shutil.rmtree(structure['temp_dir'], ignore_errors=True)
        
        session['output_file'] = output_path
        session['output_filename'] = output_filename
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download')
def download():
    if 'output_file' not in session:
        return jsonify({'error': 'No file ready'}), 400
        
    return send_file(
        session['output_file'],
        as_attachment=True,
        download_name=session.get('output_filename', 'incipit_notes.docx')
    )

@app.route('/reset', methods=['POST'])
def reset():
    session.clear()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
