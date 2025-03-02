import React, { useState, useRef, useEffect } from "react";

const MicChat = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [messages, setMessages] = useState([]);
  const mediaRecorder = useRef(null);
  const audioChunks = useRef([]);
  const streamRef = useRef(null);
  const chatRef = useRef(null);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  const startRecording = async () => {
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
    if (!mediaRecorder.current || mediaRecorder.current.state !== "recording")
      return;

    mediaRecorder.current.stop();
    setIsRecording(false);

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  };
  async function sendAudio(audioBlob) {
    const formData = new FormData();
    formData.append("file", audioBlob, "audio.wav");

    try {
      const response = await fetch("http://localhost:8000/talk", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      // Properly handle the audio stream
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

      // Convert collected chunks into a Blob and play it
      const audioBlob = new Blob(chunks, { type: "audio/mpeg" });
      const audioURL = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioURL);
      audio.play();
    } catch (error) {
      console.error("Error sending audio:", error);
    }
  }

  const clearChat = async () => {
    await fetch("http://localhost:8000/clear");
    setMessages([]);
  };

  return (
    <div style={styles.container}>
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

      <button onClick={clearChat} style={styles.clearButton}>
        Clear Chat
      </button>

      <div ref={chatRef} style={styles.chatBox}>
        {messages.map((msg, index) => (
          <p
            key={index}
            style={{
              ...styles.chatMessage,
              background: msg.role === "user" ? "#d1e7dd" : "#f8d7da",
              textAlign: msg.role === "user" ? "right" : "left",
            }}
          >
            <strong>{msg.role === "user" ? "You: " : "Bot: "}</strong>
            {msg.text}
          </p>
        ))}
      </div>

      {audioUrl && (
        <audio controls autoPlay style={{ marginTop: "10px" }}>
          <source src={audioUrl} type="audio/mpeg" />
          Your browser does not support the audio tag.
        </audio>
      )}
    </div>
  );
};

// Styles
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
  clearButton: {
    marginTop: "10px",
    padding: "5px 15px",
    cursor: "pointer",
  },
  chatBox: {
    maxWidth: "400px",
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
