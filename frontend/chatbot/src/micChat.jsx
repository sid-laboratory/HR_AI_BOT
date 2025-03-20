import React, { useState, useRef, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import Webcam from 'react-webcam';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

const MicChat = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [timeLeft, setTimeLeft] = useState(30);
  const [isTimeCompleted, setIsTimeCompleted] = useState(false);
  const [keyboardWarnings, setKeyboardWarnings] = useState([]);
  const [showWarning, setShowWarning] = useState(false);
  const [faceWarnings, setFaceWarnings] = useState([]);
  const mediaRecorder = useRef(null);
  const audioChunks = useRef([]);
  const streamRef = useRef(null);
  const chatRef = useRef(null);
  const navigate = useNavigate();
  const location = useLocation();
  const timerRef = useRef(null);
  const webcamRef = useRef(null);
  const chatHistoryRef = useRef(null);
  const warningTimeoutRef = useRef(null);
  const toastIdRef = useRef({
    keyboard: null,
    faceTilt: null,
    multipleFaces: null,
    noFace: null,
    generic: null
  });
  const faceDetectionIntervalRef = useRef(null);
  const lastToastTimeRef = useRef({
    keyboard: 0,
    faceTilt: 0,
    multipleFaces: 0,
    noFace: 0,
    generic: 0
  });
  const toastCooldownPeriod = 5000; // 5 seconds between similar toast notifications

  useEffect(() => {
    if (location.pathname === "/interview") {
      initializeSession();
    }
  }, [location.pathname]);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    if (timeLeft === 0) {
      handleTimeout();
    }
  }, [timeLeft]);

  // Add keyboard event listeners when session is active
  useEffect(() => {
    if (sessionId) {
      // Block all keyboard inputs
      window.addEventListener('keydown', handleKeyDown, true);
      window.addEventListener('keyup', handleKeyUp, true);
      
      // Start face detection when session is active
      startFaceDetection();
      
      return () => {
        window.removeEventListener('keydown', handleKeyDown, true);
        window.removeEventListener('keyup', handleKeyUp, true);
        
        // Clean up face detection interval
        if (faceDetectionIntervalRef.current) {
          clearInterval(faceDetectionIntervalRef.current);
        }
      };
    }
  }, [sessionId]);

  

  // Start face detection monitoring - increased interval to reduce processing frequency
  const startFaceDetection = () => {
    if (faceDetectionIntervalRef.current) {
      clearInterval(faceDetectionIntervalRef.current);
    }
    
    faceDetectionIntervalRef.current = setInterval(() => {
      if (webcamRef.current && sessionId) {
        const screenshot = webcamRef.current.getScreenshot();
        if (screenshot) {
          // Remove the data:image/jpeg;base64, prefix
          const base64Image = screenshot.split(',')[1];
          processFaceDetection(base64Image);
        }
      }
    }, 2000); // Check every 2 seconds instead of every second to reduce processing
  };

  // Process face detection with focus on tilt detection
  const processFaceDetection = async (base64Image) => {
    if (!sessionId) return;
    
    try {
      const response = await fetch(`http://localhost:8000/process-face?session_id=${sessionId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          image: base64Image
        }),
      });
      
      if (!response.ok) {
        console.error(`Face detection error: ${response.status}`);
        return;
      }
      
      const data = await response.json();
      
      // Process face detection warnings with rate limiting
      if (data.warnings && data.warnings.length > 0) {
        // Only process specific warnings we care about
        const currentTime = Date.now();
        
        // Check for tilt detection warnings
        if (data.tilt_detected) {
          // Only show tilt warnings if cooldown period has passed
          if (currentTime - lastToastTimeRef.current.faceTilt > toastCooldownPeriod) {
            showRateLimitedToast(`Head tilt detected (${data.tilt_direction})`, "faceTilt");
            lastToastTimeRef.current.faceTilt = currentTime;
          }
        }
        
        // Check for multiple faces
        if (data.faces_count > 1) {
          if (currentTime - lastToastTimeRef.current.multipleFaces > toastCooldownPeriod) {
            showRateLimitedToast(`Multiple faces detected (${data.faces_count} faces). Please ensure you are alone.`, "multipleFaces");
            lastToastTimeRef.current.multipleFaces = currentTime;
          }
        }
        
        // Check for no face
        if (data.faces_count === 0) {
          if (currentTime - lastToastTimeRef.current.noFace > toastCooldownPeriod) {
            showRateLimitedToast("No face detected. Please ensure your face is visible.", "noFace");
            lastToastTimeRef.current.noFace = currentTime;
          }
        }
      }
    } catch (error) {
      console.error('Error processing face detection:', error);
    }
  };

  // Show rate-limited toast notifications to prevent spamming
  const showRateLimitedToast = (message, toastType = 'generic') => {
    // If there's already an active toast of this type, don't create a new one
    // if (toastIdRef.current[toastType]) {
      // Update existing toast instead
      toast.update(toastIdRef.current[toastType], {
        render: message,
        autoClose: 6000
      });
    // }
    // } else {
      // Create new toast
      // toastIdRef.current[toastType] = toast.warning(message, {
      //   position: "top-center",
      //   autoClose: 3000,
      //   hideProgressBar: false,
      //   closeOnClick: true,
      //   pauseOnHover: true,
      //   draggable: true,
      //   onClose: () => {
      //     toastIdRef.current[toastType] = null;
      //   }
      // });
    // }
    
    // Update face warnings for the alert box
    setFaceWarnings([message]);
    setShowWarning(true);
    
    // Clear any existing timeout
    if (warningTimeoutRef.current) {
      clearTimeout(warningTimeoutRef.current);
    }
    
    // Hide warning after 3 seconds
    warningTimeoutRef.current = setTimeout(() => {
      setShowWarning(false);
    }, 3000);
  };

  // Handle keyboard events - block all keyboard inputs
  const handleKeyDown = (event) => {
    // Always prevent default behavior for any key press
    event.preventDefault();
    
    // Show toast notification for keyboard input with rate limiting
    const currentTime = Date.now();
    if (currentTime - lastToastTimeRef.current.keyboard > toastCooldownPeriod) {
      if (!toastIdRef.current.keyboard) {
        toastIdRef.current.keyboard = toast.error("Keyboard input is not allowed during the interview!", {
          position: "top-center",
          autoClose: 2000,
          hideProgressBar: false,
          closeOnClick: true,
          pauseOnHover: true,
          draggable: true,
          onClose: () => {
            toastIdRef.current.keyboard = null;
          }
        });
      }
      lastToastTimeRef.current.keyboard = currentTime;
    }
    
    // Still track the key event for backend logging
    if (sessionId) {
      trackKeyboardEvent({
        event_type: 'keydown',
        key: event.key,
        timestamp: Date.now()
      });
    }
  };

  const handleKeyUp = (event) => {
    event.preventDefault();
    
    if (sessionId) {
      trackKeyboardEvent({
        event_type: 'keyup',
        key: event.key,
        timestamp: Date.now()
      });
    }
  };

  // Track keyboard events via API
  const trackKeyboardEvent = async (eventData) => {
    try {
      const response = await fetch(`http://localhost:8000/track-keyboard?session_id=${sessionId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(eventData),
      });
      
      const data = await response.json();
      
      if (data.warnings && data.warnings.length > 0) {
        showKeyboardWarning(data.warnings);
      }
    } catch (error) {
      console.error('Error tracking keyboard event:', error);
    }
  };

  // Show keyboard warning
  const showKeyboardWarning = (warnings) => {
    setKeyboardWarnings(warnings);
    setShowWarning(true);
    
    // Clear any existing timeout
    if (warningTimeoutRef.current) {
      clearTimeout(warningTimeoutRef.current);
    }
    
    // Hide warning after 3 seconds
    warningTimeoutRef.current = setTimeout(() => {
      setShowWarning(false);
    }, 3000);
  };

  const initializeSession = async () => {
    let storedSessionId = localStorage.getItem("session_id");
    if (!storedSessionId) {
      try {
        const response = await fetch("http://localhost:8000/start-session");
        const data = await response.json();
        storedSessionId = data.session_id;
        localStorage.setItem("session_id", storedSessionId);
        resetTimer();
      } catch (error) {
        console.error("Failed to initialize session:", error);
      }
    }
    setSessionId(storedSessionId);
    fetchChatHistory(storedSessionId);
  };

  const fetchChatHistory = async (id) => {
    try {
      const response = await fetch(`http://localhost:8000/chat-history?session_id=${id}`);
      const historyData = await response.json();
      if (historyData.length > 0) {
        setMessages(historyData);
      }
    } catch (error) {
      console.error("Error fetching chat history:", error);
    }
  };

  const startRecording = async () => {
    resetTimer();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      mediaRecorder.current = new MediaRecorder(stream);
      audioChunks.current = [];

      mediaRecorder.current.ondataavailable = (event) => {
        audioChunks.current.push(event.data);
      };

      mediaRecorder.current.onstop = async () => {
        const audioBlob = new Blob(audioChunks.current, { type: "audio/webm" });
        await sendAudio(audioBlob);
      };

      mediaRecorder.current.start();
      setIsRecording(true);
    } catch (error) {
      console.error("Error accessing microphone:", error);
    }
  };

  const stopRecording = () => {
    if (!mediaRecorder.current || mediaRecorder.current.state !== "recording") return;
    mediaRecorder.current.stop();
    setIsRecording(false);

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  };

  const sendAudio = async (audioBlob = null) => {
    if (!sessionId) return;
    resetTimer(); 

    const formData = new FormData();
      
    if (audioBlob) {
      formData.append("file", audioBlob, "audio.wav"); 
    }
    formData.append("isTimeCompleted", isTimeCompleted.toString());
    try {
      const response = await fetch(`http://localhost:8000/talk?session_id=${sessionId}`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Server error urgent check: ${response.status}`);
      }
      
      // Read the audio stream
      const reader = response.body.getReader();
      const chunks = [];
      let done = false;
  
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        if (value) {
          chunks.push(value);
        }
        done = readerDone;
      }
  
      // Create a new audio blob
      const audioBlobResponse = new Blob(chunks, { type: "audio/mpeg" });
      const newAudioUrl = URL.createObjectURL(audioBlobResponse);
      setAudioUrl(newAudioUrl);
    
      setTimeout(() => {
        const audio = new Audio(newAudioUrl);
        audio.play();
      }, 100);
  
      const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;
  
      if (lastMessage && lastMessage.role !== "user") {
        timerRef.current = setInterval(() => {
          setTimeLeft((prev) => (prev > 0 ? prev - 1 : 0));
        }, 1000);
      }
  
      fetchChatHistory(sessionId);
    } catch (error) {
      console.error("Error sending audio:", error);
    }
  };

  const endInterview = () => {
    localStorage.removeItem("session_id");

    setSessionId(null);
    setMessages([]);
    navigate("/clear")
    navigate("/start_interview");
  };

  const resetTimer = () => {
    setTimeLeft(20);
    if (timerRef.current) clearInterval(timerRef.current);
    setIsTimeCompleted(false);  
  };

  const handleTimeout = () => {
    clearInterval(timerRef.current);
    console.log("User did not respond in 20 seconds. Moving to next question.");
    showRateLimitedToast("The time given to you for this question is completed. Please answer the rest on time")
    setIsTimeCompleted(true);
    sendAudio();
  };
  
  if (location.pathname === "/start_interview") {
    return (
      <div className="interview-page">
        <div className="interview-completed">
          <div className="completion-card">
            <div className="completion-icon">🎤</div>
            <h2>Welcome to the Interview Portal</h2>
            <p>Click below to start your front-end developer interview</p>
            <button className="exit-button" onClick={() => navigate("/interview")}>
              Start Interview
            </button>
          </div>
        </div>
      </div>
    );
  }
  
  return (
    <div className="interview-page">
      {/* Toast Container for notifications */}
      <ToastContainer limit={3} />
      
      <div className="interview-header">
        <h2>Front-End Developer Interview</h2>
        <div className={`timer ${timeLeft < 10 ? "timer-warning" : ""}`}>
          ⏳ {timeLeft}s
        </div>
      </div>
      
      {/* Warnings Alert Box */}
      {showWarning && (
        <div className="keyboard-warning-alert">
          <div className="warning-icon">⚠️</div>
          <div className="warning-messages">
            {keyboardWarnings.map((warning, index) => (
              <div key={`kbd-${index}`} className="warning-message">{warning}</div>
            ))}
            {faceWarnings.map((warning, index) => (
              <div key={`face-${index}`} className="warning-message">{warning}</div>
            ))}
          </div>
        </div>
      )}
      
      <div className="interview-content">
        {/* Webcam Section */}
        <div className="webcam-section">
          <Webcam
            ref={webcamRef}
            audio={false}
            screenshotFormat="image/jpeg"
            videoConstraints={{
              width: 720,
              height: 480,
              facingMode: "user"
            }}
            mirrored={true}
            className="webcam-video"
          />
          <div className="candidate-info">
            <div className="connection-status">
              <div className="status-indicator"></div>
              Excellent Connection
            </div>
            <div className="hd-indicator">HD</div>
          </div>
          <div className="webcam-instructions">Press Esc to exit fullscreen</div>
        </div>
        
        {/* Chat Section */}
        <div className="chat-section">
          <div className="chat-header">
            <h3>Interview Chat</h3>
          </div>
          
          <div className="chat-history" ref={chatRef}>
            {messages.map((msg, index) => (
              <div key={index} className={`chat-message ${msg.role === "user" ? "user-message" : "ai-message"}`}>
                <div className={`message-avatar ${msg.role}`}></div>
                <div className="message-content">
                  <div className="message-header">
                    <span className="message-sender">{msg.role === "user" ? "You" : "Interviewer"}</span>
                  </div>
                  <div className="message-text">{msg.content}</div>
                </div>
              </div>
            ))}
          </div>
          
          <div className="speech-recognition-area">
            {isRecording && (
              <div className="transcription-box">
                <div className="transcription-label">
                  <div className="recording-indicator"></div>
                  Recording in progress...
                </div>
                <div className="transcription-text">Speak now...</div>
              </div>
            )}
          </div>
          
          <div className="chat-controls">
            <button 
              className={`mic-button ${isRecording ? "recording" : ""}`} 
              onClick={isRecording ? stopRecording : startRecording}
            >
              <div className={`mic-icon ${isRecording ? "recording" : ""}`}>
                {!isRecording ? <img src="../src/assets/mic.png" alt="not there" /> : null }
              </div>
            </button>
            {isRecording && <span className="recording-indicator-text">Recording...</span>}
            <button className="end-interview-button" onClick={endInterview}>
              End Interview
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MicChat;