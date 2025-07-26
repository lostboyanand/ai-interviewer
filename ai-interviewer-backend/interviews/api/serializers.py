from rest_framework import serializers
from ..models import Candidate

class CandidateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = ['id', 'email', 'resume', 'resume_analysis', 'created_at']