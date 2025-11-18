# CiteMaven - Your Citation Expert

Transform incomplete references into perfect academic citations with CiteMaven, the intelligent citation management system that fixes what others can't.

## Features

- **Smart Citation Creation**: Transform minimal citations (e.g., "Caplan, Mind Games") into complete academic references
- **Multiple Styles**: Support for Chicago, MLA, APA, and Bluebook citation formats
- **Incipit Notes**: Convert traditional endnotes to sophisticated incipit format with page references
- **Batch Processing**: Process entire Word documents with hundreds of citations at once
- **Intelligent Lookup**: AI-powered citation completion using Open Library and custom databases

## Technology Stack

- Python/Flask backend
- Enhanced citation parsing engine
- Open Library API integration
- Custom publisher database
- XML processing for Word documents

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/citemaven.git
cd citemaven
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app_complete.py
```

4. Open your browser to `http://localhost:5000`

## Usage

### Document Processing
1. Upload a Word document (.docx) with endnotes
2. Select processing mode:
   - Smart Citation Creation (for minimal citations)
   - Format & Clean (for existing citations)
   - Incipit Notes (for page-referenced notes)
   - Complete Processing (all features)
3. Choose your citation style
4. Download the processed document

### Quick Citation
Use the Quick Citation tab to generate individual citations from minimal information.

## Deployment

This application is configured for easy deployment on Render. Simply connect your GitHub repository to Render and it will automatically deploy using the included `render.yaml` configuration.

## License

Copyright © 2024 CiteMaven. All rights reserved.

## Contact

Visit [citemaven.com](https://citemaven.com) for more information.

---

*From Fragments to Flawless - CiteMaven transforms your citations with expertise.*