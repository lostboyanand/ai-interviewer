
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


whisper_model = whisper.load_model("base")
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
        email = request.data.get('email')
        resume = request.FILES.get('resume')
        print("Calling Bedrock (Claude) for resume analysis...")
        print("Django AWS identity:", boto3.client("sts").get_caller_identity())
        # Check if email is provided
        if not email:
            return Response({
                'error': 'Email is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if email already exists
        if Candidate.objects.filter(email=email).exists():
            return Response({
                'message': 'Interview already taken',
                'details': 'Please wait, we will get back to you with your interview results soon.',
                'status': 'PENDING'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if resume is provided and is PDF
        if not resume or not resume.name.endswith('.pdf'):
            return Response({
                'error': 'PDF resume is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Create candidate first
        candidate = Candidate.objects.create(
            email=email,
            resume=resume
        )

        # Process resume
        processor = ResumeProcessor()
        resume_analysis = processor.process_resume(candidate.resume.path)
        
        # Update candidate with analysis
        candidate.resume_analysis = resume_analysis
        candidate.save()

        serializer = CandidateSerializer(candidate)
        return Response({
            'message': 'Registration successful',
            'candidate_id': candidate.id,
            'data': serializer.data,
            'resume_analysis': resume_analysis,
            'status': 'SUCCESS'
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(['POST'])
def process_response(request, interview_id):
    try:
        user_input = request.data.get('response')
        service = InterviewService()
        response = service.process_response(interview_id, user_input)
        return Response(response)
    except Exception as e:
        return Response({'error': str(e)}, status=400)


# @api_view(['POST'])
# async def process_audio_response(request, interview_id):
#     try:
#         audio_file = request.FILES.get('audio')
#         if not audio_file:
#             return Response({
#                 'error': 'Audio file is required'
#             }, status=status.HTTP_400_BAD_REQUEST)

#         # Save audio file temporarily
#         with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_audio:
#             for chunk in audio_file.chunks():
#                 temp_audio.write(chunk)
#             temp_audio_path = temp_audio.name

#         try:
#             # Transcribe audio using Whisper
#             result = whisper_model.transcribe(temp_audio_path)
#             transcribed_text = result["text"].strip()
            
#             service = InterviewService()
            
#             if not transcribed_text:
#                 # Handle silence case
#                 response = await service.handle_silence(interview_id)
#             else:
#                 # Process the transcribed text
#                 response = await service.process_response(interview_id, transcribed_text)

#             # Convert AI response to speech using Polly
#             polly_response = polly_client.synthesize_speech(
#                 Text=response['message'],
#                 OutputFormat='mp3',
#                 VoiceId='Joanna',
#                 Engine='neural'
#             )

#             # Return both text and audio
#             return Response({
#                 'text_response': response,
#                 'audio_response': polly_response['AudioStream'].read(),
#                 'transcribed_text': transcribed_text if transcribed_text else "No speech detected"
#             })

#         finally:
#             # Clean up temporary file
#             os.unlink(temp_audio_path)

#     except Exception as e:
#         return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def process_audio_response(request, interview_id):
    try:
        # Add ffmpeg to PATH with the correct path
        ffmpeg_path = r"C:\Users\2308534\Videos\test\ai-interviewer\ffmpeg-master-latest-win64-gpl-shared\ffmpeg-master-latest-win64-gpl-shared\bin"
        os.environ["PATH"] = os.environ["PATH"] + os.pathsep + ffmpeg_path
        
        audio_file = request.FILES.get('audio')
        if not audio_file:
            return Response({
                'error': 'Audio file is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check content type and use appropriate extension
        content_type = audio_file.content_type
        print(f"Received audio with content type: {content_type}")
        
        # Determine file extension based on content type
        if 'webm' in content_type:
            suffix = '.webm'
        elif 'ogg' in content_type:
            suffix = '.ogg'
        elif 'mp4' in content_type:
            suffix = '.mp4'
        else:
            suffix = '.wav'  # Default

        # Save audio file temporarily with the correct extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
            for chunk in audio_file.chunks():
                temp_audio.write(chunk)
            temp_audio_path = temp_audio.name

        try:
            # Transcribe audio using Whisper (synchronously)
            print(f"Transcribing audio file: {temp_audio_path}")
            result = whisper_model.transcribe(temp_audio_path)
            transcribed_text = result["text"].strip()
            
            service = InterviewService()
            
            if not transcribed_text:
                # Handle silence case
                response = service.handle_silence(interview_id)
            else:
                # Process the transcribed text
                response = service.process_response(interview_id, transcribed_text)

            # Convert AI response to speech using Polly
            polly_response = polly_client.synthesize_speech(
                Text=response['message'],
                OutputFormat='mp3',
                VoiceId='Joanna',
                Engine='neural'
            )

            # Get binary audio data and encode as base64
            import base64
            audio_data = polly_response['AudioStream'].read()
            encoded_audio = base64.b64encode(audio_data).decode('ascii')
            
            # Return both text and encoded audio response
            return Response({
                'text_response': response,
                'audio_response': encoded_audio,
                'transcribed_text': transcribed_text if transcribed_text else "No speech detected"
            })

        finally:
            # Clean up temporary file
            os.unlink(temp_audio_path)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
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
        from ..models import InterviewQuestion, Interview, Candidate
        InterviewQuestion.objects.all().delete()
        Interview.objects.all().delete()
        Candidate.objects.all().delete()
        return Response({'message': 'All interview data deleted.'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)