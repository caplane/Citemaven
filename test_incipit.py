#!/usr/bin/env python3
"""
Standalone Incipit Converter Test
Debug version to identify issues
"""

import xml.dom.minidom as minidom
import zipfile
import re
import os
import sys
import shutil
from pathlib import Path

def unpack_docx(docx_path, extract_dir):
    """Extract a .docx file to a directory"""
    print(f"Unpacking {docx_path}...")
    with zipfile.ZipFile(docx_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

def pack_docx(source_dir, output_path):
    """Pack a directory back into a .docx file"""
    print(f"Creating {output_path}...")
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, arcname)

def extract_endnotes(endnotes_path):
    """Extract endnote content from endnotes.xml"""
    print("Extracting endnotes...")
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
            # Remove the endnote number at the start
            full_text = re.sub(r'^\s*\d*\s*', '', full_text).strip()
            endnotes[endnote_id] = full_text
    
    return endnotes

def clean_word(word):
    """Clean a single word of punctuation"""
    word = re.sub(r'^[^\w]+', '', word)
    word = re.sub(r'[^\w]+$', '', word)
    return word

def find_context_words(text_before):
    """Extract first three words before endnote"""
    text_before = text_before.strip()
    
    if not text_before:
        return "Beginning"
    
    # Find the start of the sentence
    sentence_start = 0
    for marker in ['. ', '! ', '? ']:
        pos = text_before.rfind(marker)
        if pos > sentence_start:
            sentence_start = pos + len(marker)
    
    sentence_text = text_before[sentence_start:].strip()
    
    # Get first three clean words
    words = sentence_text.split()
    clean_words = []
    
    for word in words[:20]:  # Look at more words to find 3 clean ones
        cleaned = clean_word(word)
        if cleaned and len(cleaned) > 1:
            clean_words.append(cleaned)
        if len(clean_words) >= 3:
            break
    
    if clean_words:
        return ' '.join(clean_words[:3])
    else:
        return "Beginning"

def test_incipit_conversion(input_file):
    """Test the incipit conversion process"""
    
    print("\n" + "="*60)
    print("INCIPIT CONVERTER TEST")
    print("="*60)
    
    # Create temp directory
    temp_dir = Path('temp_incipit_test')
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()
    
    try:
        # Unpack the document
        unpack_docx(input_file, temp_dir)
        
        # Check for endnotes
        endnotes_file = temp_dir / 'word' / 'endnotes.xml'
        if not endnotes_file.exists():
            print("ERROR: No endnotes.xml found!")
            return
        
        # Extract endnotes
        endnotes = extract_endnotes(endnotes_file)
        print(f"\n✓ Found {len(endnotes)} endnotes:")
        for note_id, text in endnotes.items():
            print(f"  [{note_id}] {text[:50]}...")
        
        # Check document.xml for endnote references
        doc_file = temp_dir / 'word' / 'document.xml'
        with open(doc_file, 'r', encoding='utf-8') as f:
            doc_content = f.read()
        
        doc_dom = minidom.parseString(doc_content)
        
        # Find all endnote references in the document
        endnote_refs = doc_dom.getElementsByTagName('w:endnoteReference')
        print(f"\n✓ Found {len(endnote_refs)} endnote references in document")
        
        # Process each reference to get context
        print("\nContext extraction for each endnote:")
        print("-"*40)
        
        for ref in endnote_refs:
            ref_id = ref.getAttribute('w:id')
            
            # Find the paragraph containing this reference
            parent = ref.parentNode
            while parent and parent.tagName != 'w:p':
                parent = parent.parentNode
            
            if parent:
                # Get all text in the paragraph before the reference
                text_before = ""
                for node in parent.childNodes:
                    if node.nodeType == node.ELEMENT_NODE and node.tagName == 'w:r':
                        # Check if this run contains our reference
                        if node.getElementsByTagName('w:endnoteReference'):
                            if node.getElementsByTagName('w:endnoteReference')[0] == ref:
                                break
                        # Otherwise, get the text
                        for t in node.getElementsByTagName('w:t'):
                            if t.firstChild:
                                text_before += t.firstChild.nodeValue
                
                context = find_context_words(text_before)
                print(f"  Note {ref_id}: '{context}'")
                
                # Show some of the text before for debugging
                if text_before:
                    preview = text_before[-50:] if len(text_before) > 50 else text_before
                    print(f"    (from: ...{preview})")
        
        print("\n" + "="*60)
        print("TEST COMPLETE")
        print("\nIf the context extraction looks correct above,")
        print("the issue might be in the bookmark creation or Notes section generation.")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Try to use the test file
        test_file = "/mnt/user-data/uploads/Test_file.docx"
        if os.path.exists(test_file):
            print(f"Using test file: {test_file}")
            test_incipit_conversion(test_file)
        else:
            print("Usage: python3 test_incipit.py <input.docx>")
    else:
        test_incipit_conversion(sys.argv[1])
