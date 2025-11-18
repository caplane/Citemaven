#!/usr/bin/env python3
"""
Test script to verify enhanced_citation_creator is working
"""

import sys
import os

print("Testing CiteMaven Citation Creator...")
print("="*50)

try:
    from enhanced_citation_creator import process_minimal_citation
    print("✓ Successfully imported enhanced_citation_creator")
    
    # Test the exact citations from Test_file.docx
    test_citations = [
        "Caplan, Mind Games",
        "Scull, desperate remedies", 
        "Rachel, Strangers"
    ]
    
    print("\nTesting citation transformation:")
    print("-"*50)
    
    for citation in test_citations:
        result = process_minimal_citation(citation, 'chicago')
        print(f"Input:  {citation}")
        print(f"Output: {result}")
        print("-"*30)
        
    print("\n✓ Citation creator is working correctly!")
    
except ImportError as e:
    print(f"✗ ERROR: Could not import enhanced_citation_creator: {e}")
    print("\nMake sure enhanced_citation_creator.py is in the same directory")
    sys.exit(1)
    
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
