import { Component, OnInit, ViewChild, ElementRef, OnDestroy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import * as faceapi from 'face-api.js';

@Component({
  selector: 'app-interview',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './interview.component.html',
  styleUrls: ['./interview.component.css']
})
export class InterviewComponent implements OnInit, OnDestroy {
  @ViewChild('videoElement') videoElement!: ElementRef<HTMLVideoElement>;
  @ViewChild('canvasElement') canvasElement!: ElementRef<HTMLCanvasElement>;
  @ViewChild('audioPlayer') audioPlayer!: ElementRef<HTMLAudioElement>;

  candidateId: string = '';
  candidateData: any = {};
  resumeAnalysis: any = {};
  
  // Interview states
  interviewId: string = '';
  isChecking: boolean = true;
  isStarted: boolean = false;
  isInterviewActive: boolean = false;
  isCameraReady: boolean = false;
  isAudioReady: boolean = false;
  isNetworkReady: boolean = false;
  isCheckComplete: boolean = false;
  isRecording: boolean = false;
  isLoading: boolean = false;
  
  // Face detection props
  faceDetectionInterval: any;
  isFaceDetected: boolean = false;
  facingAway: boolean = false;
  isMultipleFaces: boolean = false;
  
  // Audio recording props
  mediaRecorder?: MediaRecorder;
  audioChunks: Blob[] = [];
  stream?: MediaStream;
  
  // Conversation tracking
  conversationHistory: { role: string, content: string }[] = [];
  currentQuestion: string = '';
  transcript: string = '';

  constructor(
    private http: HttpClient,
    private router: Router
  ) { }

  async ngOnInit() {
    // Retrieve candidate information
    this.candidateId = sessionStorage.getItem('candidate_id') || '';
    this.candidateData = JSON.parse(sessionStorage.getItem('candidate_data') || '{}');
    this.resumeAnalysis = JSON.parse(sessionStorage.getItem('resume_analysis') || '{}');
    
    if (!this.candidateId) {
      alert('Candidate information missing. Redirecting to registration.');
      this.router.navigate(['/dashboard']);
      return;
    }
    
    // Start system checks
    setTimeout(() => {
      this.startSystemCheck();
    }, 500);
  }

  async startSystemCheck() {
    try {
      // Load face-api models
      await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri('/assets/models'),
        faceapi.nets.faceLandmark68Net.loadFromUri('/assets/models'),
        faceapi.nets.faceRecognitionNet.loadFromUri('/assets/models')
      ]);
      
      // Check camera
      await this.checkCamera();
      
      // Check microphone
      await this.checkMicrophone();
      
      // Check network
      await this.checkNetwork();
      
      this.isCheckComplete = true;
    } catch (error) {
      console.error('System check failed:', error);
    }
  }
  
  async checkCamera() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ 
        video: { width: 640, height: 480 } 
      });
      
      if (this.videoElement?.nativeElement) {
        this.videoElement.nativeElement.srcObject = this.stream;
        this.videoElement.nativeElement.onloadedmetadata = () => {
          this.videoElement.nativeElement.play();
          this.testFaceDetection();
        };
        this.isCameraReady = true;
      }
    } catch (error) {
      console.error('Camera access error:', error);
    }
  }
  
  async testFaceDetection() {
    try {
      if (!this.videoElement?.nativeElement) return;
      
      const detections = await faceapi.detectSingleFace(
        this.videoElement.nativeElement, 
        new faceapi.TinyFaceDetectorOptions()
      );
      
      if (detections) {
        this.isFaceDetected = true;
      } else {
        setTimeout(() => this.testFaceDetection(), 500);
      }
    } catch (error) {
      console.error('Face detection test error:', error);
    }
  }
  
  async checkMicrophone() {
    try {
      const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Test microphone by measuring audio levels
      const audioContext = new AudioContext();
      const audioSource = audioContext.createMediaStreamSource(audioStream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      audioSource.connect(analyser);
      
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      
      // Check audio levels
      const checkAudio = () => {
        analyser.getByteFrequencyData(dataArray);
        
        // Calculate average level
        const average = dataArray.reduce((sum, value) => sum + value, 0) / bufferLength;
        
        if (average > 5) {
          // Audio detected
          this.isAudioReady = true;
          audioStream.getTracks().forEach(track => track.stop());
        } else {
          setTimeout(checkAudio, 500);
        }
      };
      
      // Give user instructions
      alert("Please make some noise (speak or tap your microphone) to test your audio.");
      checkAudio();
    } catch (error) {
      console.error('Microphone access error:', error);
    }
  }
  
  async checkNetwork() {
    try {
      const start = Date.now();
      await fetch('https://www.google.com/favicon.ico');
      const end = Date.now();
      
      const latency = end - start;
      this.isNetworkReady = latency < 1000; // Less than 1 second is acceptable
      
      if (!this.isNetworkReady) {
        alert('Your internet connection seems slow. This might affect the interview experience.');
        // Still mark as ready to not block the user
        this.isNetworkReady = true;
      }
    } catch (error) {
      console.error('Network check error:', error);
      alert('Network connectivity issues detected. Please check your internet connection.');
    }
  }
  
  startInterview() {
    this.isChecking = false;
    this.isStarted = true;
    this.isLoading = true;
    
    // Start the interview session with backend
    this.http.post<any>(`http://localhost:8000/interview/start/\${this.candidateId}/`, {})
      .subscribe(
        response => {
          this.interviewId = response.text_response.interview_id;
          this.currentQuestion = response.text_response.message;
          this.conversationHistory.push({ role: 'assistant', content: this.currentQuestion });
          
          // Play the audio response
          const audioBlob = new Blob([response.audio_response], { type: 'audio/mp3' });
          const audioUrl = URL.createObjectURL(audioBlob);
          this.audioPlayer.nativeElement.src = audioUrl;
          this.audioPlayer.nativeElement.play();
          
          // Start face monitoring
          this.startFaceMonitoring();
          
          this.isInterviewActive = true;
          this.isLoading = false;
        },
        error => {
          console.error('Error starting interview:', error);
          alert('Failed to start interview. Please try again.');
          this.isLoading = false;
        }
      );
  }
  
  startFaceMonitoring() {
    if (!this.videoElement?.nativeElement || !this.canvasElement?.nativeElement) return;
    
    const video = this.videoElement.nativeElement;
    const canvas = this.canvasElement.nativeElement;
    canvas.width = video.width;
    canvas.height = video.height;
    const context = canvas.getContext('2d');
    
    this.faceDetectionInterval = setInterval(async () => {
      if (!context) return;
      
      const detections = await faceapi.detectAllFaces(
        video, 
        new faceapi.TinyFaceDetectorOptions()
      );
      
      context.clearRect(0, 0, canvas.width, canvas.height);
      
      if (detections.length === 0) {
        this.isFaceDetected = false;
        this.facingAway = true;
      } else if (detections.length > 1) {
        this.isMultipleFaces = true;
        this.isFaceDetected = true;
        this.facingAway = false;
      } else {
        this.isFaceDetected = true;
        this.isMultipleFaces = false;
        this.facingAway = false;
        
        // Draw rectangle around face
        const detection = detections[0];
        context.beginPath();
        context.lineWidth = 3;
        context.strokeStyle = 'green';
        context.rect(
          detection.box.x, 
          detection.box.y, 
          detection.box.width, 
          detection.box.height
        );
        context.stroke();
      }
    }, 200);
  }
  
  startRecording() {
    if (!this.stream) return;
    
    this.isRecording = true;
    this.audioChunks = [];
    this.transcript = '';
    
    this.mediaRecorder = new MediaRecorder(this.stream, { mimeType: 'audio/webm' });
    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        this.audioChunks.push(event.data);
      }
    };
    
    this.mediaRecorder.onstop = () => {
      this.sendAudioResponse();
    };
    
    this.mediaRecorder.start();
  }
  
  stopRecording() {
    if (this.mediaRecorder && this.isRecording) {
      this.mediaRecorder.stop();
      this.isRecording = false;
      this.isLoading = true;
    }
  }
  
  sendAudioResponse() {
    if (this.audioChunks.length === 0) return;
    
    const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('audio', audioBlob);
    
    this.http.post<any>(`http://localhost:8000/interview/respond-audio/\${this.interviewId}/`, formData)
      .subscribe(
        response => {
          // Update UI with transcribed text
          this.transcript = response.transcribed_text;
          this.conversationHistory.push({ role: 'user', content: this.transcript });
          
          // Update UI with assistant response
          this.currentQuestion = response.text_response.message;
          this.conversationHistory.push({ role: 'assistant', content: this.currentQuestion });
          
          // Play audio response
          const responseAudioBlob = new Blob([response.audio_response], { type: 'audio/mp3' });
          const audioUrl = URL.createObjectURL(responseAudioBlob);
          this.audioPlayer.nativeElement.src = audioUrl;
          this.audioPlayer.nativeElement.play();
          
          // Check if interview is complete
          if (response.text_response.interview_status === 'COMPLETE') {
            this.endInterview();
          }
          
          this.isLoading = false;
        },
        error => {
          console.error('Error sending audio response:', error);
          alert('Failed to process your response. Please try again.');
          this.isLoading = false;
        }
      );
  }
  
  endInterview() {
    // Clear intervals and stop media streams
    if (this.faceDetectionInterval) {
      clearInterval(this.faceDetectionInterval);
    }
    
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
    }
    
    this.isInterviewActive = false;
    
    // Show completion message or redirect to results
    alert('Interview completed! Thank you for your participation.');
    // Redirect to results page or dashboard
  }
  
  ngOnDestroy() {
    // Clean up resources
    if (this.faceDetectionInterval) {
      clearInterval(this.faceDetectionInterval);
    }
    
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
    }
  }
}