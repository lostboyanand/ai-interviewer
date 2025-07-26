import fitz  
from langchain.text_splitter import RecursiveCharacterTextSplitter

class ResumeProcessor:
    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )

    def process_resume(self, pdf_path):
        try:
            # Open PDF with PyMuPDF
            doc = fitz.open(pdf_path)
            text = ""
            
            # Extract text from each page
            for page in doc:
                text += page.get_text()
            
            doc.close()
            
            # Initial analysis of resume
            resume_analysis = {
                'has_excel_experience': self._check_excel_experience(text),
                'skills': self._extract_skills(text),
                'experience': self._extract_experience(text),
                'raw_text': text
            }

            return resume_analysis

        except Exception as e:
            raise Exception(f"Error processing resume: {str(e)}")