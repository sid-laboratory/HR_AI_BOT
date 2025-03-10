import React, { useState, useRef, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";

const MicChat = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [timeLeft, setTimeLeft] = useState(30);
  const [isTimeCompleted,setIsTimeCompleted] = useState(false);
  const mediaRecorder = useRef(null);
  const audioChunks = useRef([]);
  const streamRef = useRef(null);
  const chatRef = useRef(null);
  const navigate = useNavigate();
  const location = useLocation();
  const timerRef = useRef(null);

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
    navigate("/start_interview");
  };

  const resetTimer = () => {
    setTimeLeft(20);
    if (timerRef.current) clearInterval(timerRef.current);
    setIsTimeCompleted(false);  
  };

  const  handleTimeout = () => {
    clearInterval(timerRef.current);
    console.log("User did not respond in 20 seconds. Moving to next question.");
    setIsTimeCompleted(true);
    console.log("Inside handle timeout",isTimeCompleted)
    sendAudio();
  };

  return (
    <div style={styles.container}>
      {location.pathname === "/start_interview" ? (
        <button onClick={() => navigate("/interview")} style={styles.startButton}>
          Start Interview
        </button>
      ) : (
        <>
          <h2>🎙️ Voice Chat</h2>

          <button
            onClick={isRecording ? stopRecording : startRecording}
            style={{
              ...styles.micButton,
              background: isRecording ? "red" : "blue",
            }}
          >
            🎤
          </button>
          <p>{isRecording ? "Recording..." : "Click to Start/Stop"}</p>
          <p style={{ fontSize: "18px", fontWeight: "bold" }}>⏳ Time Left: {timeLeft}s</p>

          <div ref={chatRef} style={styles.chatBox}>
            {messages.map((msg, index) => (
              <p
                key={index}
                style={{
                  ...styles.chatMessage,
                  background: msg.role === "user" ? "green" : "red",
                  textAlign: msg.role === "user" ? "right" : "left",
                }}
              >
                <strong>{msg.role === "user" ? "You: " : "Bot: "}</strong>
                {msg.content}
              </p>
            ))}
          </div>
          <button onClick={endInterview} style={styles.endButton}>
            End Interview
          </button>
        </>
      )}
    </div>
  );
};

const styles = {
  container: {
    textAlign: "center",
    marginTop: "30px",
    padding: "20px",
  },
  micButton: {
    color: "white",
    borderRadius: "50%",
    width: "80px",
    height: "80px",
    fontSize: "20px",
    cursor: "pointer",
    border: "none",
    outline: "none",
  },
  startButton: {
    padding: "10px 20px",
    fontSize: "18px",
    cursor: "pointer",
    background: "blue",
    color: "white",
    border: "none",
    borderRadius: "5px",
  },
  endButton: {
    padding: "10px 20px",
    fontSize: "18px",
    cursor: "pointer",
    background: "red",
    color: "white",
    border: "none",
    borderRadius: "5px",
    marginBottom: "10px",
  },
  clearButton: {
    marginTop: "10px",
    padding: "5px 15px",
    cursor: "pointer",
  },
  chatBox: {
    maxWidth: "600px",
    margin: "20px auto",
    padding: "10px",
    border: "1px solid #ccc",
    borderRadius: "10px",
    background: "#f9f9f9",
    textAlign: "left",
    height: "300px",
    overflowY: "auto",
  },
  chatMessage: {
    padding: "8px",
    borderRadius: "5px",
    marginBottom: "5px",
  },
};

export default MicChat;
