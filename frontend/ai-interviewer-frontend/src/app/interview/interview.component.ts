import { Component, OnInit, ViewChild, ElementRef, OnDestroy, AfterViewChecked } from '@angular/core';
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
export class InterviewComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('videoElement') videoElement!: ElementRef<HTMLVideoElement>;
  @ViewChild('canvasElement') canvasElement!: ElementRef<HTMLCanvasElement>;
  @ViewChild('audioPlayer') audioPlayer!: ElementRef<HTMLAudioElement>;
  @ViewChild('conversationHistoryDiv') conversationHistoryDiv!: ElementRef<HTMLDivElement>;
  @ViewChild('previewVideo') previewVideo!: ElementRef<HTMLVideoElement>;
  @ViewChild('previewCanvas') previewCanvas!: ElementRef<HTMLCanvasElement>;

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
  retryCount: number = 0;
  // Face detection props
  faceDetectionInterval: any;
  isFaceDetected: boolean = false;
  facingAway: boolean = false;
  isMultipleFaces: boolean = false;
  usingCdnModels: boolean = false;

  // Audio recording props
  mediaRecorder?: MediaRecorder;
  audioChunks: Blob[] = [];
  stream?: MediaStream;
  

  // Only current question and transcript
  currentQuestion: string = '';
  transcript: string = '';

  // Interview completion state
  interviewComplete: boolean = false;

  private interviewVideoAttached = false;

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
      console.log('Starting system check...');
      
      // First, let's try to check what files exist in the assets folder
      console.log('Checking if model path exists...');
      try {
        const testResponse = await fetch('/assets/models/test.txt');
        console.log('Test response status:', testResponse.status);
        console.log('Test response type:', testResponse.headers.get('content-type'));
      } catch (e) {
        console.error('Test fetch failed:', e);
      }
      
      // Log model loading attempt
      console.log('Attempting to load face-api models from /assets/models...');
      
      // Try loading models with individual error handling
      try {
        console.log('Loading tiny face detector model...');
        await faceapi.nets.tinyFaceDetector.loadFromUri('/assets/models');
        console.log('✅ Tiny face detector model loaded successfully');
      } catch (e) {
        console.error('❌ Failed to load tiny face detector model:', e);
        // Show the raw response for debugging
        try {
          const response = await fetch('/assets/models/tiny_face_detector_model-weights_manifest.json');
          const text = await response.text();
          console.log('Raw response received:', text.substring(0, 100) + '...');
        } catch (fetchErr) {
          console.error('Could not fetch model file directly:', fetchErr);
        }
      }
      
      try {
        console.log('Loading face landmark model...');
        await faceapi.nets.faceLandmark68Net.loadFromUri('/assets/models');
        console.log('✅ Face landmark model loaded successfully');
      } catch (e) {
        console.error('❌ Failed to load face landmark model:', e);
      }
      
      try {
        console.log('Loading face recognition model...');
        await faceapi.nets.faceRecognitionNet.loadFromUri('/assets/models');
        console.log('✅ Face recognition model loaded successfully');
      } catch (e) {
        console.error('❌ Failed to load face recognition model:', e);
      }
      
      console.log('Face model loading attempts completed');
      
      // As a fallback, let's try with CDN
      try {
        console.log('Trying with CDN as fallback...');
        const modelPath = 'https://justadudewhohacks.github.io/face-api.js/models';
        await Promise.all([
          faceapi.nets.tinyFaceDetector.loadFromUri(modelPath),
          faceapi.nets.faceLandmark68Net.loadFromUri(modelPath),
          faceapi.nets.faceRecognitionNet.loadFromUri(modelPath)
        ]);
        console.log('✅ Models loaded from CDN successfully');
      } catch (cdnError) {
        console.error('❌ CDN fallback also failed:', cdnError);
      }
        
      // Check camera
      console.log('Starting camera check...');
      await this.checkCamera();
      
      // Check microphone
      console.log('Starting microphone check...');
      await this.checkMicrophone();
      
      // Check network
      console.log('Starting network check...');
      await this.checkNetwork();
      
      this.isCheckComplete = true;
      console.log('System check complete!');
      // this.scrollToStartButton(); // <-- Remove or comment out this line
    } catch (error: unknown) {
      console.error('System check failed with error:', error);
      
      // Type guard to check if error is an Error object
      if (error instanceof Error) {
        console.error('Error name:', error.name);
        console.error('Error message:', error.message);
        console.error('Error stack:', error.stack);
      } else {
        console.error('Unknown error type:', typeof error);
      }
    }
  }
  
  async checkCamera() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ 
        video: { width: 320, height: 180 },
        audio: true
      });

      // Attach to preview video during system check
      if (this.previewVideo?.nativeElement) {
        this.previewVideo.nativeElement.srcObject = this.stream;
        this.previewVideo.nativeElement.muted = true;
        this.previewVideo.nativeElement.onloadedmetadata = () => {
          this.previewVideo.nativeElement.play();
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
      // Use previewVideo for system check
      const video = this.previewVideo?.nativeElement;
      if (!video) {
        console.log('Preview video element not available yet');
        return;
      }

      if (!this.isFaceDetected) {
        const options = new faceapi.TinyFaceDetectorOptions({
          inputSize: 416, // larger size for better detection
          scoreThreshold: 0.2 // lower threshold for sensitivity
        });

        try {
          const detections = await faceapi.detectSingleFace(video, options);

          if (detections) {
            this.isFaceDetected = true;
            // ...draw box if needed...
          } else {
            setTimeout(() => {
              if (!this.isFaceDetected && this.retryCount < 10) {
                this.retryCount++;
                this.testFaceDetection();
              } else if (!this.isFaceDetected) {
                this.isFaceDetected = true; // fallback to allow progress
              }
            }, 500);
          }
        } catch (error) {
          if (this.retryCount > 3) {
            this.isFaceDetected = true;
          } else {
            this.retryCount++;
            setTimeout(() => this.testFaceDetection(), 500);
          }
        }
      }
    } catch (error) {
      this.isFaceDetected = true;
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
      console.log('Checking network connectivity...');
      const start = Date.now();
      
      // Use httpbin instead of Google's favicon to avoid CORS issues
      await fetch('https://httpbin.org/status/200', { 
        mode: 'no-cors',
        cache: 'no-cache'
      });
      
      const end = Date.now();
      const latency = end - start;
      
      console.log(`Network latency: ${latency}ms`);
      this.isNetworkReady = true;
      
      if (latency > 1000) {
        console.warn('Network latency is high:', latency);
        alert('Your internet connection seems slow. This might affect the interview experience.');
      }
    } catch (error) {
      console.error('Network check error:', error);
      // Mark as true anyway to not block the user
      this.isNetworkReady = true;
      alert('Network connectivity issues detected. Please check your internet connection.');
    }
  }
  scrollToStartButton() {
    setTimeout(() => {
      const buttonElement = document.querySelector('.check-actions');
      if (buttonElement) {
        buttonElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 500);
  }


  startInterview() {
    this.isChecking = false;
    this.isStarted = true;
    this.isLoading = true;
    this.interviewVideoAttached = false;

    // Detach stream from preview video
    if (this.previewVideo?.nativeElement) {
      this.previewVideo.nativeElement.srcObject = null;
      console.log('Detached stream from previewVideo');
    }

    // Attach stream to interview video when interview starts
    if (this.videoElement?.nativeElement && this.stream) {
      this.videoElement.nativeElement.srcObject = this.stream;
      this.videoElement.nativeElement.muted = true;
      this.videoElement.nativeElement.onloadedmetadata = () => {
        this.videoElement.nativeElement.play();
      };
      if (this.videoElement.nativeElement.readyState >= 2) {
        this.videoElement.nativeElement.play();
      }
    }

    // Start the interview session with backend
    this.http.post<any>(`https://ai-interviewer-1r06.onrender.com/api/interview/start/${this.candidateId}/`, {})
      .subscribe(
        response => {
          this.interviewId = response.text_response.interview_id;
          console.log('Interview started. Interview ID:', this.interviewId);
          this.currentQuestion = response.text_response.message;
          // Decode base64 audio and play
          const binaryString = window.atob(response.audio_response);
          const bytes = new Uint8Array(binaryString.length);
          for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
          }
          const audioBlob = new Blob([bytes], { type: 'audio/mp3' });
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
    if (!this.videoElement?.nativeElement || !this.canvasElement?.nativeElement) {
      console.warn('Face monitoring: video or canvas element missing');
      return;
    }

    const video = this.videoElement.nativeElement;
    const canvas = this.canvasElement.nativeElement;
    canvas.width = video.width;
    canvas.height = video.height;
    const context = canvas.getContext('2d');

    console.log('Starting face monitoring on video:', video, 'Stream:', video.srcObject);

    this.faceDetectionInterval = setInterval(async () => {
      if (!context) return;

      // Log video readyState and if video is playing
      console.log('Face detection tick. Video readyState:', video.readyState, 'Paused:', video.paused);

      const detections = await faceapi.detectAllFaces(
        video, 
        new faceapi.TinyFaceDetectorOptions()
      );
      
      context.clearRect(0, 0, canvas.width, canvas.height);
      
      if (detections.length === 0) {
        this.isFaceDetected = false;
        this.facingAway = true;
        console.log('No face detected');
      } else if (detections.length > 1) {
        this.isMultipleFaces = true;
        this.isFaceDetected = true;
        this.facingAway = false;
        console.log('Multiple faces detected');
        detections.forEach(detection => {
          context.beginPath();
          context.lineWidth = 3;
          context.strokeStyle = 'red';
          context.rect(
            detection.box.x, 
            detection.box.y, 
            detection.box.width, 
            detection.box.height
          );
          context.stroke();
          context.fillStyle = 'rgba(255,0,0,0.10)';
          context.fillRect(
            detection.box.x, 
            detection.box.y, 
            detection.box.width, 
            detection.box.height
          );
        });
      } else {
        this.isFaceDetected = true;
        this.isMultipleFaces = false;
        this.facingAway = false;
        console.log('Single face detected:', detections[0]);
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
        // Fill with semi-transparent green
        context.fillStyle = 'rgba(0,255,0,0.15)';
        context.fillRect(
          detection.box.x, 
          detection.box.y, 
          detection.box.width, 
          detection.box.height
        );
      }
    }, 200);
  }
  
  startRecording() {
    if (!this.stream) return;
  
    this.isRecording = true;
    this.audioChunks = [];
    this.transcript = '';
  
    // Get only audio tracks from the stream
    const audioStream = new MediaStream(this.stream.getAudioTracks());
  
    // Get supported MIME types
    let options: any = {};
    let mimeType = '';
    console.log('Available MIME types:');
  
    if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
      console.log('Supported: audio/webm;codecs=opus');
      options = { mimeType: 'audio/webm;codecs=opus' };
      mimeType = 'audio/webm;codecs=opus';
    } else if (MediaRecorder.isTypeSupported('audio/webm')) {
      console.log('Supported: audio/webm');
      options = { mimeType: 'audio/webm' };
      mimeType = 'audio/webm';
    } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
      console.log('Supported: audio/mp4');
      options = { mimeType: 'audio/mp4' };
      mimeType = 'audio/mp4';
    } else if (MediaRecorder.isTypeSupported('audio/ogg')) {
      console.log('Supported: audio/ogg');
      options = { mimeType: 'audio/ogg' };
      mimeType = 'audio/ogg';
    } else {
      console.log('No supported MIME types found, using default');
      options = {};
      mimeType = '';
    }
  
    try {
      console.log('Creating MediaRecorder with options:', options);
      this.mediaRecorder = new MediaRecorder(audioStream, options);
  
      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };
  
      this.mediaRecorder.onstop = () => {
        this.sendAudioResponse();
      };
  
      this.mediaRecorder.start();
      console.log('MediaRecorder started successfully');
    } catch (error) {
      console.error('Error creating MediaRecorder:', error);
      // Try fallback to default options if not already tried
      if (Object.keys(options).length > 0) {
        try {
          console.log('Retrying MediaRecorder with default options...');
          this.mediaRecorder = new MediaRecorder(audioStream);
          this.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
              this.audioChunks.push(event.data);
            }
          };
          this.mediaRecorder.onstop = () => {
            this.sendAudioResponse();
          };
          this.mediaRecorder.start();
          console.log('MediaRecorder started successfully with default options');
          return;
        } catch (fallbackError) {
          console.error('Fallback MediaRecorder also failed:', fallbackError);
        }
      }
      this.isRecording = false;
      alert('Failed to start recording. Your browser may not support this feature or the stream does not contain audio.');
    }
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
    const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
    const audioBlob = new Blob(this.audioChunks, { type: mimeType });
    const formData = new FormData();
    formData.append('audio', audioBlob);
    this.http.post<any>(`https://ai-interviewer-1r06.onrender.com/api/interview/respond-audio/${this.interviewId}/`, formData)
      .subscribe(
        response => {
          this.transcript = response.transcribed_text;
          this.currentQuestion = response.text_response.message;
          // Decode base64 audio and play
          const binaryString = window.atob(response.audio_response);
          const bytes = new Uint8Array(binaryString.length);
          for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
          }
          const audioBlob = new Blob([bytes], { type: 'audio/mp3' });
          const audioUrl = URL.createObjectURL(audioBlob);
          this.audioPlayer.nativeElement.src = audioUrl;

          // If interview is complete, show popup only after audio ends
          if (response.interview_complete === true) {
            this.isInterviewActive = false;
            // Remove any previous event listener
            this.audioPlayer.nativeElement.onended = null;
            this.audioPlayer.nativeElement.onended = () => {
              this.interviewComplete = true;
              this.audioPlayer.nativeElement.onended = null;
            };
          }

          this.audioPlayer.nativeElement.play();
          this.isLoading = false;
        },
        error => {
          console.error('Error sending audio response:', error);
          alert('Failed to process your response. Please try again.');
          this.isLoading = false;
        }
      );
  }
  
  // End interview and show popup
  endInterview() {
    if (this.faceDetectionInterval) {
      clearInterval(this.faceDetectionInterval);
    }
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
    }
    this.isInterviewActive = false;
    this.interviewComplete = true;
  }

  // Home button handler
  goHome() {
    // Clean up and redirect to homepage/dashboard
    if (this.faceDetectionInterval) {
      clearInterval(this.faceDetectionInterval);
    }
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
    }
    this.router.navigate(['/dashboard']);
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

  ngAfterViewChecked() {
    // Attach stream to interview video after DOM is ready
    if (
      this.isStarted &&
      !this.interviewVideoAttached &&
      this.videoElement?.nativeElement &&
      this.stream
    ) {
      this.videoElement.nativeElement.srcObject = this.stream;
      this.videoElement.nativeElement.muted = true;
      this.videoElement.nativeElement.onloadedmetadata = () => {
        this.videoElement.nativeElement.play();
      };
      if (this.videoElement.nativeElement.readyState >= 2) {
        this.videoElement.nativeElement.play();
      }
      this.interviewVideoAttached = true;
    }
  }
}