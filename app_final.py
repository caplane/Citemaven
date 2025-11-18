"""
Citation Processor - With Proper Endnote Formatting (Times New Roman 10pt)
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
    Enhanced version that applies Times New Roman 10pt and proper formatting
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
            
            # Ensure paragraph has proper style
            pPr_elements = p.getElementsByTagName('w:pPr')
            if not pPr_elements:
                # Create paragraph properties
                pPr = dom.createElement('w:pPr')
                # Add as first child of paragraph
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
            
            # Add spacing after paragraph (6pt = 120 twips)
            spacing_elements = pPr.getElementsByTagName('w:spacing')
            if not spacing_elements:
                spacing = dom.createElement('w:spacing')
                spacing.setAttribute('w:after', '120')
                pPr.appendChild(spacing)
            
            # Clear all text content AFTER the endnote reference
            found_ref = False
            endnote_ref_run = None
            for child in list(p.childNodes):
                if child.nodeType == child.ELEMENT_NODE:
                    if child.tagName == 'w:r':
                        # Check if this run has the endnote reference
                        has_ref = child.getElementsByTagName('w:endnoteRef')
                        if has_ref:
                            found_ref = True
                            endnote_ref_run = child
                            # Add a space after the reference
                            space_run = dom.createElement('w:r')
                            space_text = dom.createElement('w:t')
                            space_text.setAttribute('xml:space', 'preserve')
                            space_text.appendChild(dom.createTextNode(' '))
                            space_run.appendChild(space_text)
                            # Insert space after reference
                            if child.nextSibling:
                                p.insertBefore(space_run, child.nextSibling)
                            else:
                                p.appendChild(space_run)
                        elif found_ref:
                            # This run comes after the reference - remove it
                            try:
                                p.removeChild(child)
                            except:
                                pass
            
            # Parse the formatted text to handle italics
            formatted_text = formatted[en_id]
            
            # Split text by italic markers
            parts = re.split(r'(<em>.*?</em>)', formatted_text)
            
            for part in parts:
                if not part:
                    continue
                    
                # Create new run
                new_run = dom.createElement('w:r')
                
                # Add run properties for Times New Roman 10pt
                rPr = dom.createElement('w:rPr')
                
                # Font
                rFonts = dom.createElement('w:rFonts')
                rFonts.setAttribute('w:ascii', 'Times New Roman')
                rFonts.setAttribute('w:hAnsi', 'Times New Roman')
                rFonts.setAttribute('w:cs', 'Times New Roman')
                rPr.appendChild(rFonts)
                
                # Size (20 half-points = 10pt)
                sz = dom.createElement('w:sz')
                sz.setAttribute('w:val', '20')
                rPr.appendChild(sz)
                szCs = dom.createElement('w:szCs')
                szCs.setAttribute('w:val', '20')
                rPr.appendChild(szCs)
                
                # Handle italics
                if '<em>' in part:
                    i_elem = dom.createElement('w:i')
                    rPr.appendChild(i_elem)
                    # Remove the em tags from the text
                    part = re.sub(r'</?em>', '', part)
                
                new_run.appendChild(rPr)
                
                # Add text element
                new_text = dom.createElement('w:t')
                new_text.setAttribute('xml:space', 'preserve')
                
                # Add text content
                text_content = dom.createTextNode(part)
                new_text.appendChild(text_content)
                new_run.appendChild(new_text)
                
                # Append to paragraph
                p.appendChild(new_run)
    
    # Write back
    with open(str(path), 'wb') as f:
        f.write(dom.toxml(encoding='UTF-8'))

def ensure_endnote_styles(extract_dir):
    """
    Ensure the document has proper endnote styles defined with Times New Roman 10pt
    """
    styles_path = extract_dir / 'word' / 'styles.xml'
    if not styles_path.exists():
        return
    
    try:
        dom = minidom.parse(str(styles_path))
        
        # Check if EndnoteText style exists
        has_endnote_text = False
        styles = dom.getElementsByTagName('w:style')
        for style in styles:
            style_id = style.getAttribute('w:styleId')
            if style_id == 'EndnoteText':
                has_endnote_text = True
                # Update the style to ensure Times New Roman 10pt
                # Remove old run properties
                old_rPr = style.getElementsByTagName('w:rPr')
                for rp in old_rPr:
                    style.removeChild(rp)
                
                # Add new run properties
                rPr = dom.createElement('w:rPr')
                
                # Font
                rFonts = dom.createElement('w:rFonts')
                rFonts.setAttribute('w:ascii', 'Times New Roman')
                rFonts.setAttribute('w:hAnsi', 'Times New Roman')
                rFonts.setAttribute('w:cs', 'Times New Roman')
                rPr.appendChild(rFonts)
                
                # Size
                sz = dom.createElement('w:sz')
                sz.setAttribute('w:val', '20')  # 10pt
                rPr.appendChild(sz)
                szCs = dom.createElement('w:szCs')
                szCs.setAttribute('w:val', '20')
                rPr.appendChild(szCs)
                
                style.appendChild(rPr)
                
                # Update paragraph properties
                pPr_elements = style.getElementsByTagName('w:pPr')
                if not pPr_elements:
                    pPr = dom.createElement('w:pPr')
                    style.appendChild(pPr)
                else:
                    pPr = pPr_elements[0]
                
                # Ensure spacing
                spacing_elements = pPr.getElementsByTagName('w:spacing')
                if not spacing_elements:
                    spacing = dom.createElement('w:spacing')
                    spacing.setAttribute('w:after', '120')  # 6pt after
                    spacing.setAttribute('w:line', '240')  # Single line spacing
                    spacing.setAttribute('w:lineRule', 'auto')
                    pPr.appendChild(spacing)
                
                break
        
        # If not, add it
        if not has_endnote_text:
            styles_element = dom.getElementsByTagName('w:styles')[0]
            
            # Create EndnoteText style
            new_style = dom.createElement('w:style')
            new_style.setAttribute('w:type', 'paragraph')
            new_style.setAttribute('w:styleId', 'EndnoteText')
            
            # Add name
            name_elem = dom.createElement('w:name')
            name_elem.setAttribute('w:val', 'endnote text')
            new_style.appendChild(name_elem)
            
            # Add paragraph properties
            pPr = dom.createElement('w:pPr')
            spacing = dom.createElement('w:spacing')
            spacing.setAttribute('w:after', '120')  # 6pt after
            spacing.setAttribute('w:line', '240')  # Single line spacing
            spacing.setAttribute('w:lineRule', 'auto')
            pPr.appendChild(spacing)
            new_style.appendChild(pPr)
            
            # Add run properties for Times New Roman 10pt
            rPr = dom.createElement('w:rPr')
            rFonts = dom.createElement('w:rFonts')
            rFonts.setAttribute('w:ascii', 'Times New Roman')
            rFonts.setAttribute('w:hAnsi', 'Times New Roman')
            rFonts.setAttribute('w:cs', 'Times New Roman')
            rPr.appendChild(rFonts)
            sz = dom.createElement('w:sz')
            sz.setAttribute('w:val', '20')  # 10pt
            rPr.appendChild(sz)
            szCs = dom.createElement('w:szCs')
            szCs.setAttribute('w:val', '20')
            rPr.appendChild(szCs)
            new_style.appendChild(rPr)
            
            styles_element.appendChild(new_style)
        
        # Save updated styles
        with open(str(styles_path), 'wb') as f:
            f.write(dom.toxml(encoding='UTF-8'))
            
    except Exception as e:
        print(f"Could not update styles: {e}")

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
        
        # Ensure proper styles are defined
        ensure_endnote_styles(extract_dir)
        
        # Check for endnotes
        endnotes_file = extract_dir / 'word' / 'endnotes.xml'
        if not endnotes_file.exists():
            return jsonify({'error': 'No endnotes found in document'}), 400
        
        # Extract endnotes
        endnotes = extract_endnotes(endnotes_file)
        print(f'✔ Extracted {len(endnotes)} endnotes')
        
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
        
        print(f'✔ Formatted {len(formatted_endnotes)} citations in {style} style')
        
        # Update endnotes.xml with proper styles
        update_endnotes_xml(endnotes_file, formatted_endnotes)
        print(f'✔ Updated endnotes.xml with Times New Roman 10pt')
        
        # Pack back into docx
        original_filename = secure_filename(file.filename)
        output_filename = f"formatted_{original_filename}"
        output_path = temp_dir / output_filename
        pack_docx(extract_dir, output_path)
        print(f'✔ Created {output_filename}')
        
        # Read into memory before cleanup
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
        
        # Cleanup on error
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
        
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
