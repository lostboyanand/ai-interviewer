from langchain.memory import ConversationBufferMemory
from langchain_aws import ChatBedrock
from ..models import Interview, Candidate, InterviewQuestion
from django.db import models
from django.conf import settings
import boto3
import datetime
import os 
import json 
 # Check if response is wrapped in code blocks
import re

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

    


    def start_interview(self, candidate_id):
        """Start a new interview session or resume an existing one"""
        try:
            candidate = Candidate.objects.get(id=candidate_id)
            # Check if there's an existing incomplete interview
            existing_interview = Interview.objects.filter(
                candidate=candidate,
                interview_complete=False
            ).first()
            if existing_interview:
                # Resume existing interview
                greeting_prompt = f"""
                You are Anjali from Coding Ninjas resuming an Excel technical interview.
                We were in the middle of an interview that was interrupted. The candidate is returning to continue.
                Current question number: {existing_interview.current_question}
                Please:
                1. Welcome them back warmly
                2. Say that we'll continue the interview from where we left off
                3. Briefly remind them of what we were discussing (based on the last exchange)
                4. Either repeat the last question OR move to a new question if appropriate
                Do not reintroduce yourself or restart the interview process.
                Be natural and conversational in your response.
                """
                # Get the last exchange if available
                if existing_interview.transcript and len(existing_interview.transcript) >= 2:
                    last_question = existing_interview.transcript[-2]["text"] if existing_interview.transcript[-2]["speaker"] == "interviewer" else None
                    if last_question:
                        greeting_prompt += f"\n\nThe last question asked was: '{last_question}'"
                response = self.llm.invoke(greeting_prompt)
                response_text = response.content if hasattr(response, "content") else str(response)
                self._update_transcript(existing_interview, "interviewer", response_text)
                return {
                    'interview_id': existing_interview.id,
                    'message': response_text,
                    'status': 'RESUMED'
                }
            else:
                # Start new interview (original code)
                interview = Interview.objects.create(
                    candidate=candidate,
                    status='ACTIVE',
                    current_question=0
                )
                resume_context = candidate.resume_analysis
                greeting_prompt = f"""
                You are an advanced AI technical interviewer representing Coding Ninjas. Your name is Anjali, and you need to introduce both yourself and mention that your colleague Kuldeep Naruka will be present during the interview.

                Resume Context: {resume_context['raw_text']}

                Begin with a professional greeting that:
                1. Introduces yourself as Anjali from Coding Ninjas
                2. Explicitly mentions that your colleague Kuldeep Naruka will be present and listening during the interview
                3. Welcomes the candidate warmly to this Excel technical assessment
                4. Briefly mentions the interview will evaluate their Excel proficiency through a series of questions
                5. Asks for the candidate's name

                Important guidelines:
                - NEVER use placeholder text like "[Your Name]" - your name is Anjali 
                - Clearly state that "My colleague Kuldeep Naruka will be present and listening to our conversation"
                - Maintain a friendly yet professional tone appropriate for Coding Ninjas' brand
                - Keep your introduction concise (4-5 sentences maximum)
                - Sound natural and conversational, not robotic
                - Do not mention that you are an AI - present yourself as a human interviewer
                - if you dont know the interview is starting, just say "Hello, I am Anjali from Coding Ninjas. My colleague Kuldeep Naruka will be present and listening to our conversation. what is your name ? can you introduce yourself?"
                """
                response = self.llm.invoke(greeting_prompt)
                response_text = response.content if hasattr(response, "content") else str(response)
                self._update_transcript(interview, "interviewer", response_text)
                return {
                    'interview_id': interview.id,
                    'message': response_text,
                    'status': 'STARTED'
                }
        except Exception as e:
            raise Exception(f"Error starting interview: {str(e)}")


    def process_response(self, interview_id, user_input):
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
        # Generate brief feedback and next question
        
        # Generate next question based on interview phase
        next_question = self._generate_next_question(interview)
        
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

    def _generate_next_question(self, interview):
        """
        Generate next question based on context and phase.
        Interview flow:
        0: greeting (not counted)
        1: resume question #1
        2: resume question #2
        3: excel question #1
        4: excel question #2
        5: excel question #3
        6+: final feedback
        """
        context = self.memory.load_memory_variables({})
        current_question = interview.current_question
        if current_question < 2:  # 0,1
            # Resume-based questions phase
            return self._generate_resume_question(interview)
        elif current_question < 5:  # 2,3,4
            # Excel questions phase
            return self._generate_excel_question(interview)
        else:  # 5 and above
            # Complete interview
            return self._generate_final_feedback(interview)

    def _generate_resume_question(self, interview):
        """Generate a question based on candidate's resume"""
        candidate = interview.candidate
        resume_data = candidate.resume_analysis
        # Increment question counter
        interview.current_question += 1
        interview.save()
        # Get previous response if this is question 2
        previous_response = None
        if interview.current_question == 2:
            try:
                prev_exchanges = interview.transcript[-2:]  # Get last question and answer
                if len(prev_exchanges) >= 2:
                    previous_response = prev_exchanges[1]["text"]  # The candidate's response
            except Exception:
                pass
        # Format prompt based on resume data
        prompt = f"""
        You are Anjali  from Coding Ninjas conducting an Excel technical interview.

        Candidate's resume: {resume_data['raw_text']}
        This is question #{interview.current_question} of the interview.

        GUIDELINES FOR QUESTION CREATION:

        If the resume DOES mention Excel skills (has_excel_experience: {resume_data.get('has_excel_experience', False)}):
        - Look for specific Excel-related keywords like: formulas, VLOOKUP, macros, pivot tables, data analysis, charts, dashboards, etc.
        - Ask about a SPECIFIC Excel element you identified in their resume. For example: "I see you mentioned experience with pivot tables in your resume. Could you explain a complex scenario where you used them effectively?"
        - If they mention general Excel proficiency without specifics, ask about their strongest Excel skill or a challenging Excel problem they've solved

        If the resume DOES NOT mention Excel skills:
        - ABSOLUTELY DO NOT ask if they have used or have experience with Excel in any way
        - INSTEAD, create a strategic question that ASSUMES they will use Excel and asks HOW they would approach a specific task
        - For example: "Given your background in [specific skill from resume], how would you use Excel to [specific task related to their field]?"
        - Or: "If you needed to analyze [type of data relevant to their experience] using Excel, what approach would you take?"

        FORBIDDEN PHRASES - DO NOT USE THESE:
        - "Have you ever used Excel"
        - "Have you had experience with Excel"
        - "Are you familiar with Excel"
        - "Have you worked with Excel"
        - Any variation that asks about their Excel experience directly

        {"The candidate's previous response was: " + previous_response if interview.current_question == 2 else ""}

        QUESTION REQUIREMENTS:
        1. Make it conversational and natural, as one human interviewer to a candidate
        2. Focus on ONE clear question only
        3. Phrase it to reveal their problem-solving approach with Excel, not their experience level
        4. DO NOT introduce yourself again - you've already been introduced
        5. Address the candidate by name if appropriate, but don't worry about using their name if it flows better without it

        IF this is question #2 (interview.current_question == 2):
        - Start with a BRIEF (1-2 sentence) constructive comment on their previous answer
        - Decide whether to:
        a) Ask a follow-up question based on their previous response if they mentioned something Excel-related or relevant to Excel
        b) OR ask a completely new question if their previous response didn't provide a good opportunity for follow-up
        - Prioritize follow-up questions when possible as they create a more natural conversation flow

        DO NOT include any formatting instructions in your response.
        DO NOT prefix your question with labels or tags.
        Just provide the natural conversational response directly.
        """
        # Generate question
        question = self.llm.invoke(prompt)
        question_text = question.content if hasattr(question, "content") else str(question)
        InterviewQuestion.objects.create(
            interview=interview,
            question_number=interview.current_question,
            question_text=question_text,
            question_type='resume_based'
        )
        return question_text

    def _generate_excel_question(self, interview):
        """Generate an Excel-specific question with hybrid difficulty progression and adaptivity"""
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
        base_difficulty = difficulty_map.get(excel_proficiency, 'moderate')

        # Calculate which Excel question number this is (1-based)
        excel_question_number = interview.current_question - 2  # Subtract 2 resume questions

        # Default difficulty progression
        if excel_question_number == 1:
            # First Excel question - start at base difficulty
            difficulty = base_difficulty
        elif excel_question_number == 2:
            # Second Excel question - increase difficulty one level
            if base_difficulty == 'easy':
                difficulty = 'moderate'
            else:
                difficulty = 'difficult'
        elif excel_question_number == 3:
            # Third Excel question - maintain or raise difficulty
            difficulty = 'difficult'
        else:
            difficulty = 'difficult'  # Default for any additional questions

        # Get the candidate's previous response
        previous_response = None
        prev_question = None
        try:
            prev_exchanges = interview.transcript[-2:]  # Get last question and answer
            if len(prev_exchanges) >= 2:
                previous_response = prev_exchanges[1]["text"]  # The candidate's response
                # Get the previous question
                prev_question = InterviewQuestion.objects.filter(
                    interview=interview,
                    question_number=interview.current_question-1
                ).latest('created_at')
        except Exception:
            pass

        # Score previous answer if one exists
        if previous_response and prev_question:
            try:
                scoring_prompt = f"""
                You are an Excel assessment expert. Rate the following answer to an Excel technical question:
                
                Question: {prev_question.question_text}
                Answer: {previous_response}
                
                On a scale of 1-10, provide only a number score for this answer based on these guidelines:
                    - 1-3: Completely incorrect or nonsensical answer
                    - 4-5: Shows basic understanding but with significant gaps or errors
                    - 6-7: Generally correct answer with minor misunderstandings
                    - 8-10: Technically accurate and complete answer

                Be generous in your scoring when there's partial understanding.
                Consider the complexity of the question when scoring.
                For verbal responses, focus on conceptual understanding rather than exact syntax.
                
                Return only the numeric score, nothing else.
                """
                # Get score
                score_response = self.llm.invoke(scoring_prompt)
                score_text = score_response.content if hasattr(score_response, "content") else str(score_response)
                # Extract numeric score
                import re
                score_match = re.search(r'\b([0-9]|10)\b', score_text)
                if score_match:
                    score = int(score_match.group(1))
                    # Save score to previous question
                    prev_question.score = score
                    prev_question.save()
                    # Adjust difficulty based on performance, but with limits
                    if score < 4:
                        prev_question.feedback = f"Your answer shows basic understanding but lacks key technical details about {prev_question.question_type.replace('excel_', '')} Excel concepts."

                        # Lower difficulty but never below base_difficulty
                        if difficulty == 'difficult':
                            difficulty = 'moderate'
                        elif difficulty == 'moderate' and base_difficulty == 'easy':
                            difficulty = 'easy'
                    elif score > 7:
                        prev_question.feedback = f"Excellent answer that shows strong technical proficiency in {prev_question.question_type.replace('excel_', '')} Excel skills."
                        # Push to difficult if they're excelling
                        difficulty = 'difficult'
                    # Print debug info
                    elif score > 4 and score <= 7:
                        prev_question.feedback = f"Excellent answer that shows strong technical proficiency in {prev_question.question_type.replace('excel_', '')} Excel skills."
                    print(f"Q{excel_question_number}: Base: {base_difficulty}, Score: {score}, Final: {difficulty}")
            except Exception as e:
                print(f"Error scoring answer: {str(e)}")

        prompt = f"""
        You are Anjali from Coding Ninjas conducting an Excel technical interview. Generate a {difficulty} level Excel question.

        This is question #{interview.current_question} of the interview.

        {"The candidate's previous response was: " + previous_response if previous_response else "This is your first Excel-specific question."}

        For context, here's how the interview has gone so far:
        {self._format_transcript_summary(transcript)}

        FEEDBACK GUIDELINES:
        - If the previous answer was technically accurate and complete, start with "That's excellent! You've demonstrated strong understanding of [concept]."
        - If the previous answer had minor issues but was mostly correct, start with "That's a good effort. You understand the basics of [concept], but..."
        - If the previous answer was incorrect or missed key points, start with "Let's clarify how [concept] actually works."
        - ALWAYS use a unique introduction for each question - do not repeat the same phrases across questions
        - NEVER start consecutive questions with the same phrase

        The question should test actual Excel knowledge and be specific enough to gauge technical proficiency.
        For {difficulty} difficulty:
        - Easy: Basic functions, simple formulas, or interface questions
        - Moderate: VLOOKUP, HLOOKUP, IF statements, PivotTables, or basic data analysis
        - Difficult: Complex nested functions, advanced PivotTables, Power Query, macros, or VBA concepts

        QUESTION GUIDELINES:
        1. If needed based on the feedback criteria above, start with a BRIEF (1-2 sentence) constructive comment on their previous answer
        2. Then ask ONE clear, focused Excel question at the appropriate difficulty level
        3. The question should be conversational and natural, as a human interviewer would ask
        4. It should require technical knowledge but be answerable verbally

        Make sure your question is specific enough to evaluate their Excel knowledge but doesn't require them to actually demonstrate it on a computer.

        DO NOT include any formatting instructions or labels in your response.
        DO NOT start your response with "QUESTION FORMAT:" or similar text.
        Just provide the natural conversational response directly.
        """
        # Generate question
        question = self.llm.invoke(prompt)
        question_text = question.content if hasattr(question, "content") else str(question)
        # Record this question
        InterviewQuestion.objects.create(
            interview=interview,
            question_number=interview.current_question,
            question_text=question_text,
            question_type=f'excel_{difficulty}'
        )
        return question_text
        
    def _generate_final_feedback(self, interview):
        """Generate final feedback and complete the interview"""
        # Update interview status
        interview.status = 'COMPLETED'
        interview.interview_complete = True  # Mark as complete
        interview.save()
        # Analyze the full transcript
        transcript = interview.transcript
        candidate = interview.candidate
        candidate_name = None
        # Try to extract candidate name from transcript
        for item in transcript:
            if item['speaker'] == 'candidate' and len(item['text']) < 100:
                # Simple heuristic: first short response is likely their name
                candidate_name = item['text'].strip()
                break
        # Generate detailed report (saved to DB, not returned to user)
        detailed_report = self._generate_detailed_report(interview)
        interview.detailed_report = detailed_report
        # Calculate final score based on question scores
        questions = InterviewQuestion.objects.filter(interview=interview)
        if questions.exists():
            avg_score = questions.aggregate(models.Avg('score'))['score__avg'] or 0
            interview.final_score = avg_score
        # Format prompt for user-facing feedback
        user_feedback_prompt = f"""
        You've just completed an Excel technical interview with {candidate_name or "the candidate"}. 
        Create a brief, positive, and encouraging conclusion to the interview that:
        1. Thanks them by name (if available, otherwise say "Thank you") for participating in the interview
        2. Includes 1-2 positive observations about their performance (be authentic but encouraging)
        3. Mentions 1-2 Excel topics they might want to further explore to improve their skills (be tactful)
        4. Ends with a note that HR will be in touch with them soon regarding next steps
        Important:
        - Be conversational and human-like
        - Don't mention scores or grades
        - Keep it brief (3-5 sentences)
        - Maintain a positive, encouraging tone
        - Sound natural, like how a human interviewer would conclude
        Example Style (but use your own words and tailor to THIS candidate):
        "Thank you [name] for a great interview today! I was particularly impressed with your knowledge of [specific strength]. To further enhance your Excel skills, you might want to explore more about [topic]. Our HR team will be in touch with you soon about next steps. Have a great day!"
        """
        # Generate user feedback
        user_feedback = self.llm.invoke(user_feedback_prompt)
        user_feedback_text = user_feedback.content if hasattr(user_feedback, "content") else str(user_feedback)
        # Save the feedback to the interview model
        interview.feedback = {
            'user_feedback': user_feedback_text,
            'generated_at': datetime.datetime.now().isoformat()
        }
        interview.save()
        return user_feedback_text

    def _generate_detailed_report(self, interview):
        """Generate an extremely detailed report with scoring for each question for HR use"""
        import json
        questions = InterviewQuestion.objects.filter(interview=interview)
        candidate = interview.candidate
        # Get all questions and answers
        qa_pairs = []
        for q in questions:
            qa_pairs.append({
                "question_number": q.question_number,
                "question": q.question_text,
                "answer": q.answer or "No answer provided",
                "question_type": q.question_type,
                "score": q.score
            })
        # Get resume context
        resume_context = candidate.resume_analysis
        # Format the entire transcript for context
        transcript_text = self._format_transcript(interview.transcript)
        detailed_prompt = f"""
        You are an advanced Excel technical assessment expert. Create an EXTREMELY DETAILED interview report for HR.
        CANDIDATE INFORMATION:
        Resume Summary: {resume_context.get('raw_text', 'No resume available')}
        FULL INTERVIEW TRANSCRIPT:
        {transcript_text}
        QUESTION AND ANSWER ASSESSMENT:
        {json.dumps(qa_pairs, indent=2)}
        Create an EXTREMELY COMPREHENSIVE analysis with the following sections:
        1. EXECUTIVE SUMMARY
           - Overall assessment (1-2 paragraphs)
           - Final numerical score (0-100)
           - Excel proficiency level (Beginner/Intermediate/Advanced/Expert)
           - Recommendation for hiring (Strong Yes/Yes/Maybe/No)
        2. TECHNICAL SKILLS ASSESSMENT
           - Detailed breakdown by Excel skill category:
             * Formula knowledge (Basic/Intermediate/Advanced) with examples from answers
             * Data manipulation capabilities
             * Analytical thinking
             * Pivot Table proficiency
             * Data visualization understanding
             * Automation knowledge (macros/VBA if discussed)
             * Any other relevant technical areas
        3. QUESTION-BY-QUESTION ANALYSIS
           - For each question, provide:
             * Question intent (what skill/knowledge was being tested)
             * Scoring justification (why the score was given)
             * Strengths in the answer
             * Gaps or misconceptions identified
             * Recommendations for improvement
        4. SOFT SKILLS ASSESSMENT
           - Communication clarity
           - Problem-solving approach
           - Thought process articulation
           - Technical vocabulary usage
           - Confidence level
        5. CANDIDATE STRENGTHS
           - Minimum 3-5 specific strengths with examples from the interview
        6. DEVELOPMENT AREAS
           - Minimum 3-5 specific improvement areas with examples
           - Recommended resources for each area (courses, books, practice exercises)
        7. CULTURAL FIT ASSESSMENT
           - Work style indicators from responses
           - Potential team fit considerations
        8. COMPARISON TO TYPICAL EXCEL USER PROFILES
           - How the candidate compares to typical Excel user profiles (Analyst, Data Processor, Dashboard Creator, etc.)
        9. FINAL RECOMMENDATION
           - Role suitability
           - Growth potential
           - Suggested follow-up questions for future interviews
        Be EXTREMELY detailed, providing specific examples from the interview to support each point.
        Focus on actionable insights for HR and hiring managers.
        This report will be used to make hiring decisions and for candidate feedback.
        """
        # Generate the detailed analysis
        analysis = self.llm.invoke(detailed_prompt)
        analysis_text = analysis.content if hasattr(analysis, "content") else str(analysis)
        # Create report structure
        report = {
            "candidate_id": str(candidate.id),
            "candidate_email": candidate.email,
            "interview_id": interview.id,
            "interview_date": interview.created_at.isoformat(),
            "detailed_analysis": analysis_text,
            "question_count": questions.count(),
            "question_breakdown": [
                {
                    "question_number": q.question_number,
                    "question_text": q.question_text,
                    "answer_text": q.answer or "No answer provided",
                    "question_type": q.question_type,
                    "score": q.score or 0,
                    "feedback": getattr(q, 'feedback', None) or "No feedback provided"
                } for q in questions
            ],
            "generated_at": datetime.datetime.now().isoformat()
        }
        return report

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

    
    def analyze_job_candidates(self, job_title, job_description, candidate_data):
        """
        Analyze candidates against job requirements.
        
        Args:
            job_title: The title of the job position
            job_description: Detailed description of the job requirements
            candidate_data: List of candidate interview data
            
        Returns:
            Analysis results and recommendations
        """
        # Enhance candidate data with their resume information
        enhanced_candidate_data = []
        
        for candidate in candidate_data:
            try:
                # Get the interview
                interview = Interview.objects.get(id=candidate['interview_id'])
                # Get the candidate's resume analysis
                resume_data = interview.candidate.resume_analysis
                
                # Add resume data to candidate info
                enhanced_candidate = candidate.copy()
                enhanced_candidate['resume_data'] = resume_data
                enhanced_candidate_data.append(enhanced_candidate)
            except (Interview.DoesNotExist, AttributeError, KeyError) as e:
                # If something goes wrong, just use the original data
                enhanced_candidate_data.append(candidate)
                print(f"Error enhancing candidate data: {e}")
        
        analysis_prompt = f"""
        You are an AI talent matching specialist for a technical recruitment team.

        JOB REQUIREMENT:
        Title: {job_title}
        Description: {job_description}

        CANDIDATE DATA:
        {json.dumps(enhanced_candidate_data)}

        TASK:
        1. Analyze the job requirements and thoroughly review each candidate's data including:
        - Their resume information (in resume_data field)
        - Their interview performance (detailed_report)
        - Their responses to technical questions
        
        2. CREATE A BALANCED ASSESSMENT that considers:
        - Technical skills from the resume that match the job requirements
        - Soft skills and problem-solving ability demonstrated in the interview
        - Excel skills as an indicator of analytical capability
        
        3. Identify the TOP 3 most suitable candidates for this position (or fewer if there aren't 3 candidates).
        
        4. For each recommended candidate, provide:
        - Ranking position (1, 2, 3)
        - Candidate email
        - Interview ID
        - Match score (percentage from 0-100%)
        - Strengths (at least 3 key strengths, prioritizing skills that match the job requirements)
        - Development areas (areas where candidate needs improvement relative to the job requirements)
        - Recommendation - In 2-3 sentences that:
            * Highlight specific skills from the resume that match the job requirements
            * Note transferable skills demonstrated in the Excel interview
            * Provide an overall assessment of fit for {job_title} position
            * Mention potential for growth

        FORMAT YOUR RESPONSE AS JSON:
        {{
        "top_candidates": [
            {{
            "rank": 1,
            "interview_id": 123,
            "candidate_email": "email@example.com",
            "match_score": 85,
            "strengths": ["strength1", "strength2", "strength3"],
            "gaps": ["gap1", "gap2"],
            "recommendation": "Balanced recommendation mentioning both resume skills and interview performance..."
            }},
            ...
        ],
        "analysis_summary": "Overall analysis connecting resume qualifications to job requirements..."
        }}

        Ensure your analysis gives appropriate weight to skills mentioned in the resume that directly match the job requirements, while also considering the analytical abilities demonstrated in the Excel interview.
        """
        
        response = self.llm.invoke(analysis_prompt)
        response_text = response.content if hasattr(response, "content") else str(response)
        
        # Try to parse the response as JSON
        try:
            # Check if response is wrapped in code blocks
            import re
            json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', response_text, re.DOTALL)
            if json_match:
                recommendations = json.loads(json_match.group(1))
            else:
                recommendations = json.loads(response_text)
            return recommendations
        except json.JSONDecodeError:
            # Return raw text if JSON parsing fails
            return {
                "error": "Failed to parse AI response",
                "raw_analysis": response_text
            }
        

    def handle_silence(self, interview_id):
        """Handle when no audio response is detected"""
        interview = Interview.objects.get(id=interview_id)
        
        reminder_message = "I didn't hear your response. Could you please answer the question, or let me know if you need me to repeat or clarify anything?"
        
        # Store in transcript
        self._update_transcript(interview, "interviewer", reminder_message)
        
        return {
            'message': reminder_message,
            'status': interview.status
        }