
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ..models import Candidate
from .serializers import CandidateSerializer
from ..services.resume_processor import ResumeProcessor 

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