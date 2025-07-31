from django.urls import path
from . import views

urlpatterns = [
    path('test/', views.test_view, name='test-view'),
    path('register/', views.register_candidate, name='register-candidate'),
    path('interview/start/<uuid:candidate_id>/', views.start_interview, name='start-interview'),
    path('interview/respond/<int:interview_id>/', views.process_response, name='process-response'),
    path('interview/respond-audio/<int:interview_id>/', views.process_audio_response, name='process-audio-response'),
    path('interview/report/<int:interview_id>/', views.get_interview_report, name='get-interview-report'),
    path('delete-all/', views.delete_all_data, name='delete-all-data'),
    path('interview/responses/', views.get_interview_responses, name='get-interview-responses'),
    path('hr/login/', views.hr_login, name='hr-login'),
    path('smart-requirement/', views.smart_requirement_analysis, name='smart-requirement-analysis'),
]