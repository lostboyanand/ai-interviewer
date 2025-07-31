
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ..models import Candidate
from .serializers import CandidateSerializer
from ..services.resume_processor import ResumeProcessor 
from ..services.interview_service import InterviewService
import whisper
import boto3
import tempfile
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from asgiref.sync import async_to_sync
from ..models import InterviewQuestion, Interview, Candidate ,HRUser
from django.views.decorators.csrf import csrf_exempt
whisper_model = whisper.load_model("tiny")
polly_client = boto3.client('polly' , region_name='us-east-1')

@api_view(['GET'])
def test_view(request):
    return Response({
        "message": "Hello from AI Interviewer API!",
        "status": "success"
    })


@api_view(['POST'])
def register_candidate(request):
    try:
        print("register_candidate called")
        email = request.data.get('email')
        resume = request.FILES.get('resume')
        print(f"Received email: {email}")
        print(f"Received resume: {resume}")
        print("Calling Bedrock (Claude) for resume analysis...")
        print("Django AWS identity:", boto3.client("sts").get_caller_identity())
        
        # Check if email is provided
        if not email:
            print("No email provided")
            return Response({
                'error': 'Email is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if email already exists
        if Candidate.objects.filter(email=email).exists():
            print(f"Candidate with email {email} already exists")
            return Response({
                'message': 'Interview already taken',
                'details': 'Please wait, we will get back to you with your interview results soon.',
                'status': 'PENDING'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if resume is provided and is PDF
        if not resume or not resume.name.endswith('.pdf'):
            print(f"Invalid or missing resume: {resume}")
            return Response({
                'error': 'PDF resume is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        print("Creating Candidate object...")
        candidate = Candidate.objects.create(
            email=email,
            resume=resume
        )
        print(f"Candidate created with ID: {candidate.id}")

        # Process resume
        processor = ResumeProcessor()
        print(f"Processing resume at path: {candidate.resume.path}")
        resume_analysis = processor.process_resume(candidate.resume.path)
        print(f"Resume analysis result: {resume_analysis}")
        
        # Update candidate with analysis
        candidate.resume_analysis = resume_analysis
        candidate.save()
        print("Candidate updated with resume analysis.")

        serializer = CandidateSerializer(candidate)
        print("Candidate serialized successfully.")
        return Response({
            'message': 'Registration successful',
            'candidate_id': candidate.id,
            'data': serializer.data,
            'resume_analysis': resume_analysis,
            'status': 'SUCCESS'
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        import traceback
        print("Exception occurred in register_candidate:")
        print(traceback.format_exc())
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(['POST'])
def process_response(request, interview_id):
    try:
        user_input = request.data.get('response')
        service = InterviewService()
        response = service.process_response(interview_id, user_input)
        # Check if interview is complete
        
        interview = Interview.objects.get(id=interview_id)
        return Response({
            **response,
            'interview_complete': interview.interview_complete
        })
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
def smart_requirement_analysis(request):
    """Analyze candidates based on job description"""
    try:
        # Get data from request
        job_title = request.data.get('job_title')
        job_description = request.data.get('job_description')
        
        if not job_title or not job_description:
            return Response({
                'error': 'Job title and description are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get all completed interviews with detailed reports
        interviews = Interview.objects.filter(
            interview_complete=True,
            detailed_report__isnull=False
        ).select_related('candidate')
        
        if not interviews:
            return Response({
                'error': 'No completed interviews found for analysis'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Format candidate data for analysis
        candidate_data = []
        for interview in interviews:
            candidate_data.append({
                'interview_id': interview.id,
                'candidate_email': interview.candidate.email,
                'final_score': interview.final_score,
                'detailed_report': interview.detailed_report,
            })
        
        # Use the interview service for analysis
        service = InterviewService()
        recommendations = service.analyze_job_candidates(job_title, job_description, candidate_data)
        
        return Response({
            'job_title': job_title,
            'job_description': job_description,
            'recommendations': recommendations
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def process_audio_response(request, interview_id):
    try:
        ffmpeg_path = r"C:\Users\2308534\Videos\Project\ai-interviewer\ai-interviewer-backend\ffmpeg-master-latest-win64-gpl-shared\ffmpeg-master-latest-win64-gpl-shared\bin"
        os.environ["PATH"] = os.environ["PATH"] + os.pathsep + ffmpeg_path
        audio_file = request.FILES.get('audio')
        if not audio_file:
            return Response({
                'error': 'Audio file is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        content_type = audio_file.content_type
        print(f"Received audio with content type: {content_type}")
        if 'webm' in content_type:
            suffix = '.webm'
        elif 'ogg' in content_type:
            suffix = '.ogg'
        elif 'mp4' in content_type:
            suffix = '.mp4'
        else:
            suffix = '.wav'  # Default
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
            for chunk in audio_file.chunks():
                temp_audio.write(chunk)
            temp_audio_path = temp_audio.name
        try:
            print(f"Transcribing audio file: {temp_audio_path}")
            result = whisper_model.transcribe(temp_audio_path ,
                                            language="en",  
                                            fp16=False,    
                                            beam_size=1 )
            transcribed_text = result["text"].strip()
            service = InterviewService()
            if not transcribed_text:
                response = service.handle_silence(interview_id)
            else:
                response = service.process_response(interview_id, transcribed_text)
            # Check if interview is complete
            
            interview = Interview.objects.get(id=interview_id)
            polly_response = polly_client.synthesize_speech(
                Text=response['message'],
                OutputFormat='mp3',
                VoiceId='Joanna',
                Engine='standard'
            )
            import base64
            audio_data = polly_response['AudioStream'].read()
            encoded_audio = base64.b64encode(audio_data).decode('ascii')
            return Response({
                'text_response': response,
                'audio_response': encoded_audio,
                'transcribed_text': transcribed_text if transcribed_text else "No speech detected",
                'interview_complete': interview.interview_complete
            })
        finally:
            os.unlink(temp_audio_path)
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
# New endpoint: Get detailed interview report for HR


# New endpoint: Get all interview emails and dates
@api_view(['GET'])
def get_interview_responses(request):
    """Return all interview candidate emails, interview ids, and interview dates."""
    interviews = Interview.objects.select_related('candidate').all().order_by('-created_at')
    data = [
        {
            'interview_id': interview.id,
            'email': interview.candidate.email,
            'interview_date': interview.created_at
        }
        for interview in interviews
    ]
    return Response({'interviews': data})

@api_view(['GET'])
def get_interview_report(request, interview_id):
    """Get the detailed interview report (protected endpoint for HR)"""
    try:
        interview = Interview.objects.get(id=interview_id)
        if not interview.detailed_report:
            return Response({
                'error': 'No report available for this interview'
            }, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'interview_id': interview_id,
            'candidate_email': interview.candidate.email,
            'detailed_report': interview.detailed_report,
            'final_score': interview.final_score,
            'interview_complete': interview.interview_complete,
            'interview_date': interview.created_at
        })
    except Interview.DoesNotExist:
        return Response({
            'error': 'Interview not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['POST'])
def start_interview(request, candidate_id):
    try:
        service = InterviewService()
        
        # Call the interview service
        response = service.start_interview(candidate_id)
        
        # Regular synchronous call to Polly
        polly_response = polly_client.synthesize_speech(
            Text=response['message'],
            OutputFormat='mp3',
            VoiceId='Joanna',
            Engine='neural'
        )
        
        # Get audio data - this is binary
        audio_data = polly_response['AudioStream'].read()
        
        # Return binary data as base64
        import base64
        encoded_audio = base64.b64encode(audio_data).decode('ascii')
        
        # Return both text and encoded audio response
        return Response({
            'text_response': response,
            'audio_response': encoded_audio
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['POST'])
def delete_all_data(request):
    try:
        # Delete all InterviewQuestion, Interview, and Candidate records
        
        InterviewQuestion.objects.all().delete()
        Interview.objects.all().delete()
        Candidate.objects.all().delete()
        return Response({'message': 'All interview data deleted.'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)




@csrf_exempt
@api_view(['POST'])
def hr_login(request):
    """
    HR login endpoint. Expects JSON: { "email": "...", "password": "..." }
    """
    email = request.data.get('email')
    password = request.data.get('password')
    if not email or not password:
        return Response({'success': False, 'error': 'Email and password required.'}, status=400)
    try:
        user = HRUser.objects.get(email=email)
        if user.password == password:
            return Response({'success': True, 'message': 'Login successful.'})
        else:
            return Response({'success': False, 'error': 'Invalid credentials.'}, status=401)
    except HRUser.DoesNotExist:
        return Response({'success': False, 'error': 'Invalid credentials.'}, status=401)