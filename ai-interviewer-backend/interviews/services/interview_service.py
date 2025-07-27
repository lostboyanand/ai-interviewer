from langchain.memory import ConversationBufferMemory
from langchain_aws import ChatBedrock
from ..models import Interview, Candidate, InterviewQuestion
from django.db import models
from django.conf import settings
import boto3
import datetime
import os 

os.environ["AWS_ACCESS_KEY_ID"] = settings.AWS_ACCESS_KEY_ID
os.environ["AWS_SECRET_ACCESS_KEY"] = settings.AWS_SECRET_ACCESS_KEY
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


class InterviewService:
    def __init__(self):
        self.llm = ChatBedrock(
            model_id="amazon.titan-text-premier-v1:0"
            # model_id="anthropic.claude-3-sonnet-20240229-v1:0"
        )
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        # Initialize Polly for voice
        self.polly = boto3.client(
        service_name='polly',
        region_name=settings.AWS_DEFAULT_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
    )

    async def start_interview(self, candidate_id):
        """Start a new interview session"""
        try:
            candidate = Candidate.objects.get(id=candidate_id)
            
            # Create new interview
            interview = Interview.objects.create(
                candidate=candidate,
                status='ACTIVE'
            )

            # Initial greeting with context from resume
            resume_context = candidate.resume_analysis
            
            greeting_prompt = f"""
            You are an expert Excel technical interviewer. The candidate's resume shows:
            {resume_context['raw_text']}
            
            Start the interview professionally:
            1. Greet the candidate
            2. Ask for their name
            3. Maintain a friendly yet professional tone
            
            Keep the greeting brief and natural.
            """

            response = await self.llm.predict(greeting_prompt)
            
            # Store in transcript
            self._update_transcript(interview, "interviewer", response)
            
            return {
                'interview_id': interview.id,
                'message': response,
                'status': 'STARTED'
            }

        except Exception as e:
            raise Exception(f"Error starting interview: {str(e)}")

    async def process_response(self, interview_id, user_input):
        """Process candidate's response and generate next question"""
        interview = Interview.objects.get(id=interview_id)
        
        # Add to memory
        self.memory.save_context(
            {"input": user_input},
            {"output": ""}
        )

        # Store candidate's response
        self._update_transcript(interview, "candidate", user_input)
        
        # If this was an answer to a question, save it to the InterviewQuestion
        if interview.current_question > 0:
            try:
                question = InterviewQuestion.objects.filter(
                    interview=interview,
                    question_number=interview.current_question
                ).latest('created_at')
                question.answer = user_input
                question.save()
            except InterviewQuestion.DoesNotExist:
                pass

        # Generate next question based on interview phase
        next_question = await self._generate_next_question(interview)
        
        # Store interviewer's question
        self._update_transcript(interview, "interviewer", next_question)

        return {
            'message': next_question,
            'status': interview.status
        }

    def _update_transcript(self, interview, speaker, text):
        """Update the interview transcript"""
        if not interview.transcript:
            interview.transcript = []
        
        interview.transcript.append({
            "speaker": speaker,
            "text": text,
            "timestamp": datetime.datetime.now().isoformat()
        })
        interview.save()

    async def _generate_next_question(self, interview):
        """Generate next question based on context and phase"""
        context = self.memory.load_memory_variables({})
        current_question = interview.current_question

        if current_question < 2:
            # Resume-based questions phase
            return await self._generate_resume_question(interview)
        elif current_question < 5:
            # Excel questions phase
            return await self._generate_excel_question(interview)
        else:
            # Complete interview
            return await self._generate_final_feedback(interview)
    
    async def _generate_resume_question(self, interview):
        """Generate a question based on candidate's resume"""
        candidate = interview.candidate
        resume_data = candidate.resume_analysis
        
        # Increment question counter
        interview.current_question += 1
        interview.save()
        
        # Format prompt based on resume data
        prompt = f"""
        You are conducting an Excel technical interview. The candidate's resume shows:
        {resume_data['raw_text']}
        
        Based on their resume, generate a thoughtful question about their Excel experience or skills.
        If Excel skills are mentioned (has_excel_experience: {resume_data.get('has_excel_experience', False)}), 
        focus on their specific Excel experience.
        
        If no Excel skills are mentioned, ask a general question about their experience that might relate to Excel usage.
        
        The question should be conversational and direct. This is question #{interview.current_question} of the interview.
        Ask only ONE clear question.
        """
        
        # Generate question
        question = await self.llm.predict(prompt)
        
        # Record this question
        InterviewQuestion.objects.create(
            interview=interview,
            question_number=interview.current_question,
            question_text=question,
            question_type='resume_based'
        )
        
        return question

    async def _generate_excel_question(self, interview):
        """Generate an Excel-specific question"""
        # Load the transcript to assess performance
        transcript = interview.transcript
        candidate = interview.candidate
        
        # Increment question counter
        interview.current_question += 1
        interview.save()
        
        # Format prompt for Excel question based on proficiency
        excel_proficiency = candidate.resume_analysis.get('excel_proficiency', 'Intermediate')
        
        # Map proficiency to difficulty
        difficulty_map = {
            'Beginner': 'easy',
            'Intermediate': 'moderate',
            'Advanced': 'difficult', 
            'Expert': 'difficult'
        }
        
        difficulty = difficulty_map.get(excel_proficiency, 'moderate')
        
        # Adjust difficulty based on previous answers if available
        if interview.current_question > 3:
            # Get previous question's answer and adjust difficulty
            try:
                prev_question = InterviewQuestion.objects.get(
                    interview=interview,
                    question_number=interview.current_question-1
                )
                
                if prev_question.score:
                    if prev_question.score < 3:  # Struggling
                        difficulty = 'easy'
                    elif prev_question.score > 7:  # Doing well
                        difficulty = 'difficult'
            except InterviewQuestion.DoesNotExist:
                pass
        
        prompt = f"""
        You are conducting an Excel technical interview. Generate a {difficulty} level Excel question.
        
        This is question #{interview.current_question} of the interview.
        
        For context, here's how the interview has gone so far:
        {self._format_transcript_summary(transcript)}
        
        The question should test actual Excel knowledge and be specific enough to gauge technical proficiency.
        For {difficulty} difficulty:
        - Easy: Basic functions, simple formulas, or interface questions
        - Moderate: VLOOKUP, HLOOKUP, IF statements, PivotTables, or basic data analysis
        - Difficult: Complex nested functions, advanced PivotTables, Power Query, macros, or VBA concepts
        
        Ask only ONE clear question.
        """
        
        # Generate question
        question = await self.llm.predict(prompt)
        
        # Record this question
        InterviewQuestion.objects.create(
            interview=interview,
            question_number=interview.current_question,
            question_text=question,
            question_type=f'excel_{difficulty}'
        )
        
        return question
        
    async def _generate_final_feedback(self, interview):
        """Generate final feedback and complete the interview"""
        # Update interview status
        interview.status = 'COMPLETED'
        interview.save()
        
        # Analyze the full transcript
        transcript = interview.transcript
        
        # Format prompt for final feedback
        prompt = f"""
        You've just completed an Excel technical interview. Please analyze the entire conversation and provide comprehensive feedback:
        
        Full interview transcript:
        {self._format_transcript(transcript)}
        
        Please provide:
        1. Overall assessment of the candidate's Excel skills (score out of 100)
        2. Strengths demonstrated during the interview
        3. Areas for improvement
        4. Specific recommendations for skill development
        5. Final conclusion about the candidate's Excel proficiency level
        
        Structure your response clearly with these sections.
        """
        
        # Generate feedback
        feedback = await self.llm.predict(prompt)
        
        # Save feedback
        interview.feedback = {
            'feedback_text': feedback,
            'generated_at': datetime.datetime.now().isoformat()
        }
        
        # Generate detailed report (this would be more structured)
        detailed_report = await self._generate_detailed_report(interview)
        interview.detailed_report = detailed_report
        
        # Calculate final score based on question scores
        questions = InterviewQuestion.objects.filter(interview=interview)
        if questions.exists():
            avg_score = questions.aggregate(models.Avg('score'))['score__avg'] or 0
            interview.final_score = avg_score
        
        interview.save()
        
        return feedback

    def _determine_question_difficulty(self, interview):
        """Determine the difficulty of the next question based on performance"""
        # Get previous questions and their scores
        previous_questions = InterviewQuestion.objects.filter(
            interview=interview,
            question_type__startswith='excel_'
        )
        
        # Default to moderate for first Excel question
        if not previous_questions.exists():
            return 'moderate'
        
        # Get the latest Excel question's score
        latest_excel_q = previous_questions.latest('created_at')
        
        if latest_excel_q.score is None:
            return 'moderate'
        
        # Adjust difficulty based on score
        if latest_excel_q.score < 3:  # Struggling
            return 'easy'
        elif latest_excel_q.score > 7:  # Doing well
            return 'hard'
        else:
            return 'moderate'

    def _format_transcript_summary(self, transcript):
        """Format a brief summary of the transcript for context"""
        if not transcript:
            return "No previous conversation."
            
        summary = []
        for item in transcript[-6:]:  # Last 6 exchanges only
            speaker = item['speaker']
            text = item['text'][:100] + "..." if len(item['text']) > 100 else item['text']
            summary.append(f"{speaker.upper()}: {text}")
        
        return "\n".join(summary)

    def _format_transcript(self, transcript):
        """Format the complete transcript"""
        if not transcript:
            return "No conversation recorded."
            
        formatted = []
        for item in transcript:
            formatted.append(f"{item['speaker'].upper()}: {item['text']}")
        
        return "\n".join(formatted)

    async def _generate_detailed_report(self, interview):
        """Generate a detailed report with scoring for each question"""
        questions = InterviewQuestion.objects.filter(interview=interview)
        
        # Prepare prompt with all Q&A
        qa_pairs = []
        for q in questions:
            qa_pairs.append({
                "question": q.question_text,
                "answer": q.answer or "No answer provided",
                "question_type": q.question_type
            })
        
        prompt = f"""
        You are an Excel assessment expert. Analyze each question and answer pair from this interview:
        
        {qa_pairs}
        
        For each question-answer pair, provide:
        1. Score (0-10)
        2. Specific feedback on the answer
        3. What was good about the answer
        4. What could be improved
        
        Then provide an overall assessment of the candidate's Excel proficiency level 
        (Beginner, Intermediate, Advanced, Expert).
        """
        
        # Generate analysis
        analysis = await self.llm.predict(prompt)
        
        # Create structured report
        report = {
            "question_analysis": [],
            "overall_assessment": analysis,
            "generated_at": datetime.datetime.now().isoformat()
        }
        
        return report

    async def handle_silence(self, interview_id):
        """Handle when no audio response is detected"""
        interview = Interview.objects.get(id=interview_id)
        
        reminder_message = "I didn't hear your response. Could you please answer the question, or let me know if you need me to repeat or clarify anything?"
        
        # Store in transcript
        self._update_transcript(interview, "interviewer", reminder_message)
        
        return {
            'message': reminder_message,
            'status': interview.status
        }