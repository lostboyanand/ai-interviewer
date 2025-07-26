from django.urls import path
from . import views

urlpatterns = [
    path('test/', views.test_view, name='test-view'),
    path('register/', views.register_candidate, name='register-candidate'),
]