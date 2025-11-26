import os
import zipfile
import shutil
import tempfile
import re
import uuid
import logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, session
from werkzeug.utils import secure_filename
import xml.etree.ElementTree as ET

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'incipit-genie-production-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# XML Namespaces
NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'xml': 'http://www.w3.org/XML/1998/namespace'
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

def qn(tag):
    return f"{{{NS['w']}}}{tag}"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'docx'

# ==========================================
#  CORE LOGIC: INCIPIT EXTRACTOR
# ==========================================

class IncipitExtractor:
    def __init__(self, word_count=3):
        self.word_count = word_count
    
    def get_sentence_start(self, text, position):
        """
        Backtracks to find the start of the sentence, handling 'Dr.', 'Mr.', etc.
        """
        text_before = text[:position]
        if not text_before:
            return ""

        # Negative Lookbehind to avoid splitting on Dr., Mr., etc.
        pattern = (
            r'(?<!Dr)(?<!Mr)(?<!Ms)(?<!Mrs)(?<!Prof)(?<!Rev)(?<!Sen)(?<!Rep)'
            r'(?<=[.?!])\s+(?=[A-Z])'
        )
        sentences = re.split(pattern, text_before)
        if not sentences:
            return ""
            
        current_sentence = sentences[-1].strip()
        current_sentence = re.sub(r'^["\'\u201c\u2018\s]+', '', current_sentence)
        
        words = current_sentence.split()
        selected_words = words[:self.word_count]
        
        if selected_words:
            # Clean trailing punctuation
            selected_words[-1] = re.sub(r'[.,;:!?"\'\u201d\u2019]+$', '', selected_words[-1])
            
        return ' '.join(selected_words)

    def extract_contexts(self, doc_tree):
        """Map Endnote IDs to their Incipit text."""
        contexts = {}
        for p in doc_tree.iter(qn('p')):
            runs_data = []
            for child in p:
                if child.tag == qn('r'):
                    t_elem = child.find(qn('t'))
                    text_content = t_elem.text if (t_elem is not None and t_elem.text) else ""
                    
                    ref = child.find(qn('endnoteReference'))
                    e_id = ref.get(qn('id')) if ref is not None else None
                    
                    runs_data.append({'text': text_content, 'id': e_id})
            
            current_pos = 0
            full_para_text = "".join([r['text'] for r in runs_data])
            
            for run in runs_data:
                current_pos += len(run['text'])
                if run['id']:
                    contexts[run['id']] = self.get_sentence_start(full_para_text, current_pos)
                    
        return contexts

# ==========================================
#  CORE LOGIC: DOCUMENT TRANSFORMER
# ==========================================

def process_document_xml(doc_tree, endnotes_tree, contexts, format_bold=True, keep_superscripts=False):
    """
    1. Replaces endnotes in body with Bookmarks.
    2. Builds new 'Notes' section preserving URLs.
    """
    
    # 1. Map IDs to Bookmarks (Body Processing)
    ref_map = {}
    bookmark_id_counter = 10000
    
    # Locate all endnote references
    refs_to_process = []
    for p in doc_tree.iter(qn('p')):
        for r in p.findall(qn('r')):
            ref = r.find(qn('endnoteReference'))
            if ref is not None:
                refs_to_process.append((p, r, ref))

    for parent_p, run, ref in refs_to_process:
        e_id = ref.get(qn('id'))
        if e_id in ['0', '-1']: continue

        b_name = f"REF_NOTE_{e_id}"
        b_id = str(bookmark_id_counter)
        bookmark_id_counter += 1
        ref_map[e_id] = b_name
        
        # Insert Bookmark
        bm_start = ET.Element(qn('bookmarkStart'), {qn('id'): b_id, qn('name'): b_name})
        bm_end = ET.Element(qn('bookmarkEnd'), {qn('id'): b_id})
        
        p_children = list(parent_p)
        try:
            r_index = p_children.index(run)
            parent_p.insert(r_index, bm_start)
            parent_p.insert(r_index + 2, bm_end)
            
            # If user wants to hide superscripts, remove the reference element
            if not keep_superscripts:
                run.remove(ref)
                t = run.find(qn('t'))
                if t is not None: run.remove(t)
                
        except ValueError:
            continue

    # 2. Build Notes Section
    notes_container = []
    
    # Header
    header_p = ET.Element(qn('p'))
    pPr = ET.SubElement(header_p, qn('pPr'))
    ET.SubElement(pPr, qn('pStyle'), {qn('val'): 'Heading1'})
    r = ET.SubElement(header_p, qn('r'))
    t = ET.SubElement(r, qn('t'))
    t.text = "Notes"
    notes_container.append(header_p)
    
    sorted_ids = sorted([eid for eid in ref_map.keys()], key=lambda x: int(x) if x.isdigit() else 0)
    endnotes_map = {e.get(qn('id')): e for e in endnotes_tree.findall(qn('endnote'))}

    for e_id in sorted_ids:
        original_note = endnotes_map.get(e_id)
        if original_note is None: continue
            
        note_p = ET.Element(qn('p'))
        pPr = ET.SubElement(note_p, qn('pPr'))
        ET.SubElement(pPr, qn('pStyle'), {qn('val'): 'EndnoteText'})
        
        # A. Page Number Field (PAGEREF)
        b_name = ref_map[e_id]
        instr_text = f" PAGEREF {b_name} \\h "
        fldSimple = ET.SubElement(note_p, qn('fldSimple'), {qn('instr'): instr_text})
        r_fld = ET.SubElement(fldSimple, qn('r'))
        ET.SubElement(r_fld, qn('t')).text = "0"
        
        # B. Separator
        r_sep = ET.SubElement(note_p, qn('r'))
        ET.SubElement(r_sep, qn('t'), {qn('space'): 'preserve'}).text = ". "
        
        # C. Incipit Text
        incipit = contexts.get(e_id, "")
        if incipit:
            r_inc = ET.SubElement(note_p, qn('r'))
            rPr_inc = ET.SubElement(r_inc, qn('rPr'))
            if format_bold: ET.SubElement(rPr_inc, qn('b'))
            else: ET.SubElement(rPr_inc, qn('i'))
            
            ET.SubElement(r_inc, qn('t')).text = incipit
            
            # Colon
            r_col = ET.SubElement(note_p, qn('r'))
            ET.SubElement(r_col, qn('t'), {qn('space'): 'preserve'}).text = ": "

        # D. Original Content (Preserving Links!)
        # We iterate over children of the original paragraphs to keep hyperlinks
        for child_p in original_note.findall(qn('p')):
            for child in child_p:
                if child.tag == qn('pPr'): continue # Skip paragraph props
                if child.find(qn('endnoteRef')) is not None: continue # Skip the superscript number
                
                # Append the run or hyperlink directly to our new paragraph
                note_p.append(child)
        
        notes_container.append(note_p)

    # 3. Append to Body
    body = doc_tree.find(qn('body'))
    
    # Page Break
    br_p = ET.Element(qn('p'))
    br_r = ET.SubElement(br_p, qn('r'))
    ET.SubElement(br_r, qn('br'), {qn('type'): 'page'})
    body.append(br_p)
    
    for p in notes_container:
        body.append(p)
        
    return len(sorted_ids)

# ==========================================
#  ROUTES
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400

    # Get Form Data
    try:
        word_count = int(request.form.get('word_count', 3))
    except: word_count = 3
    
    format_style = request.form.get('format_style', 'bold') == 'bold'
    keep_superscripts = request.form.get('keep_superscripts') == 'yes'

    # Process
    temp_dir = Path(app.config['UPLOAD_FOLDER']) / f"proc_{uuid.uuid4().hex}"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        filename = secure_filename(file.filename)
        input_path = temp_dir / filename
        output_filename = f"Incipit_{filename}"
        output_path = temp_dir / output_filename
        
        file.save(input_path)
        
        # 1. Extract
        with zipfile.ZipFile(input_path, 'r') as z:
            z.extractall(temp_dir)
            
        doc_xml_path = temp_dir / 'word' / 'document.xml'
        endnotes_xml_path = temp_dir / 'word' / 'endnotes.xml'
        
        if not endnotes_xml_path.exists():
            return jsonify({'error': 'Document has no endnotes'}), 400
            
        # 2. Parse & Transform
        doc_tree = ET.parse(str(doc_xml_path))
        endnotes_tree = ET.parse(str(endnotes_xml_path))
        
        extractor = IncipitExtractor(word_count)
        contexts = extractor.extract_contexts(doc_tree)
        
        process_document_xml(doc_tree, endnotes_tree, contexts, format_style, keep_superscripts)
        
        doc_tree.write(str(doc_xml_path), encoding='UTF-8', xml_declaration=True)
        
        # 3. Repack
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
            for file_path in temp_dir.rglob('*'):
                if file_path.is_file() and file_path.name != output_filename:
                    arcname = file_path.relative_to(temp_dir)
                    z.write(file_path, arcname)
                    
        return send_file(
            output_path,
            as_attachment=True,
            download_name=output_filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.route('/preview', methods=['POST'])
def preview():
    return jsonify([
        {'raw': 'Preview requires full processing.', 'processed': 'Please Convert to see full results.', 'type': 'System'}
    ])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
