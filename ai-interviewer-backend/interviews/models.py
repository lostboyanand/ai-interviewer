from django.db import models

from django.db import models

import uuid

class Candidate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    resume = models.FileField(upload_to='resumes/', null=False, blank=False) 
    resume_analysis = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

class Interview(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='ACTIVE')
    current_question = models.IntegerField(default=0)
    last_interaction = models.DateTimeField(auto_now=True)
    feedback = models.JSONField(null=True, blank=True)
    detailed_report = models.JSONField(null=True, blank=True)
    transcript = models.JSONField(null=True, blank=True)  # Store complete conversation
    final_score = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Interview for {self.candidate.email}"

class InterviewQuestion(models.Model):
    interview = models.ForeignKey(Interview, on_delete=models.CASCADE)
    question_number = models.IntegerField()
    question_text = models.TextField()
    answer = models.TextField(null=True, blank=True)
    feedback = models.TextField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    question_type = models.CharField(max_length=20)  # resume_based, excel_basic, excel_advanced
    response_time = models.IntegerField(null=True)  # in seconds
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Q{self.question_number} for {self.interview.candidate.email}"