import fitz  
from langchain.text_splitter import RecursiveCharacterTextSplitter
import json
from langchain_aws import ChatBedrock
from django.conf import settings
import os



os.environ["AWS_ACCESS_KEY_ID"] = settings.AWS_ACCESS_KEY_ID
os.environ["AWS_SECRET_ACCESS_KEY"] = settings.AWS_SECRET_ACCESS_KEY
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


class ResumeProcessor:
    def __init__(self):
        self.llm = ChatBedrock(
            model_id="amazon.titan-text-premier-v1:0",
            model_kwargs={
                "temperature": 0,
                "max_tokens": 1024,
                "stopSequences": [],
                "topP": 1
            }
        )
        
    def process_resume(self, pdf_path):
        try:
            # Extract text from PDF
            doc = fitz.open(pdf_path)
            text = ""
            
            for page in doc:
                text += page.get_text()
            
            doc.close()
            
            # Use Claude to analyze the resume
            prompt = f"""
            I need you to analyze this resume for an Excel technical interview:

            {text}

            Please provide the following analysis in JSON format:
            1. has_excel_experience: true/false - determine if the person has Excel experience
            2. skills: extract all relevant technical skills, especially Excel-related skills
            3. experience: extract a summary of their work experience
            4. excel_proficiency: estimate their Excel proficiency level (Beginner, Intermediate, Advanced, Expert)
            
            Return ONLY valid JSON without explanation or any other text.
            """
            
            response = self.llm.invoke(prompt)
            
            # response_body = json.loads(response['body'].read())
            # analysis_text = response_body['content'][0]['text']
            
            # Parse the JSON response
            try:
                analysis = json.loads(response)
                # Add the raw text to the analysis
                analysis['raw_text'] = text
                return analysis
            except json.JSONDecodeError:
                # If Claude didn't return proper JSON, create a basic structure
                return {
                    'has_excel_experience': False,
                    'skills': [],
                    'experience': "Could not extract experience",
                    'excel_proficiency': "Unknown",
                    'raw_text': text
                }

        except Exception as e:
            raise Exception(f"Error processing resume: {str(e)}")