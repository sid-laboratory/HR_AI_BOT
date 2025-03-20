from fastapi import FastAPI, UploadFile, Query, Form, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any, List
import speech_recognition as sr
from pydub import AudioSegment
from dotenv import load_dotenv
import pyttsx3
import os
import json
import requests
import time
import uuid
import redis
import base64
import numpy as np
import cv2

# Import the FaceDetector class
from face_detector import FaceDetector

# Import the KeyboardTracker class
class KeyboardTracker:
    def __init__(self):
        self.active = True
        self.allowed_keys = set([
            # Navigation keys
            "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", 
            "Home", "End", "PageUp", "PageDown",
            # Form navigation
            "Tab", "Enter", "Escape", "Space",
            # Number keys (for multiple choice)
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
            # Letter keys for typing answers
            "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
            "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
            "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
            "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
            # Punctuation for typing
            ".", ",", "!", "?", ":", ";", "-", "(", ")", "[", "]", "'", "\"",
            # Common modifier keys
            "Shift", "Control"
        ])
        
        self.forbidden_key_combinations = [
            ["Control", "c"], # Copy
            ["Control", "v"], # Paste
            ["Control", "x"], # Cut
            ["Control", "f"], # Find
            ["Alt", "Tab"], # Switch windows
            ["Control", "Tab"], # Switch tabs
            ["Control", "t"], # New tab
            ["Control", "n"], # New window
            ["F12"], # Developer tools
            ["Control", "Shift", "i"], # Developer tools
            ["Control", "Shift", "j"], # Developer tools
        ]
        
        self.active_keys = set()
        self.key_history = []
        self.history_size = 20
        self.last_warning_time = 0
        self.warning_cooldown = 2  # Seconds between warnings
    
    def set_allowed_keys(self, keys: List[str]):
        """Set the list of allowed keys."""
        self.allowed_keys = set(keys)
    
    def track(self, event_data: Dict[str, Any]) -> Optional[List[str]]:
        """
        Track keyboard events and check for violations.
        
        Args:
            event_data: Dictionary containing keyboard event information
                - event_type: 'keydown', 'keyup'
                - key: Key that was pressed
                - timestamp: Event timestamp
                
        Returns:
            List of warning messages or None if no violations
        """
        if not self.active:
            return None
            
        warnings = []
        event_type = event_data.get("event_type")
        key = event_data.get("key", "")
        
        current_time = time.time()
        
        # Update active keys
        if event_type == "keydown":
            self.active_keys.add(key)
            
            # Record key press in history
            self.key_history.append({
                "key": key,
                "time": current_time
            })
            
            # Trim history if needed
            if len(self.key_history) > self.history_size:
                self.key_history = self.key_history[-self.history_size:]
            
            # Check if key is allowed
            if key not in self.allowed_keys and current_time - self.last_warning_time > self.warning_cooldown:
                warnings.append(f"Unauthorized key pressed: {key}")
                self.last_warning_time = current_time
            
            # Check for forbidden key combinations
            for combo in self.forbidden_key_combinations:
                if all(k in self.active_keys for k in combo) and current_time - self.last_warning_time > self.warning_cooldown:
                    warnings.append(f"Forbidden key combination detected: {'+'.join(combo)}")
                    self.last_warning_time = current_time
        
        elif event_type == "keyup":
            if key in self.active_keys:
                self.active_keys.remove(key)
        
        return warnings if warnings else None

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

app = FastAPI()

origins = [
    "http://localhost:5174",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Store KeyboardTracker instances for each session
keyboard_trackers = {}

# Store FaceDetector instances for each session
face_detectors = {}

@app.get("/start-session")
async def start_session():
    """Create a new session and return a unique session_id."""
    session_id = str(uuid.uuid4())  # Generate a unique session ID
    initial_prompt = [{
        "role": "system",
        "content": "You are interviewing the user for a front-end React developer position and his name is Sid. Ask short questions relevant to a junior-level developer. Keep responses under 30 words and be strict with grading. Please also don't tell the answer to the user until and unless he completely gives up on the answer and does not know anything. Also, ask him questions again and again, don't conclude the interview.Please be super strict with the interview and grading"
    }]
    redis_client.set(f"session:{session_id}", json.dumps(initial_prompt))
    
    # Create a keyboard tracker for this session
    keyboard_trackers[session_id] = KeyboardTracker()
    
    # Create a face detector for this session
    face_detectors[session_id] = FaceDetector(
        min_detection_confidence=0.5,
        movement_threshold=0.1,
        history_size=10
    )
    
    return {"session_id": session_id}


@app.get("/chat-history")
async def get_chat_history(session_id: str = Query(..., description="Session ID")):
    """Fetch chat history for a given session."""
    return load_messages(session_id)

@app.post("/talk")
async def post_audio(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = None,
    isTimeCompleted: str = Form(...), 
    session_id: str = Query(..., description="Session ID"),
):
    """Process user speech, generate response, and store in Redis."""
    is_time_completed = isTimeCompleted.lower() == "true"
    
    try:
        if is_time_completed or not file:
            user_message = "I wasn't able to answer within the time limit."
        else:
            result = await transcribe_audio(file)
            user_message = result["text"]
            
            # If speech recognition failed, use a default message
            if user_message == "Could not understand the audio" or user_message == "Speech recognition request failed":
                user_message = "Sorry, I couldn't be heard clearly."
        
        # Generate response from AI
        chat_response, response_time = get_chat_response(user_message, session_id)
        
        # Save messages to Redis
        save_messages(session_id, user_message, chat_response)
        
        # Convert response to speech
        audio_file_path = text_to_speech(chat_response)
        
        # Schedule file deletion after sending response
        background_tasks.add_task(delete_audio_file, audio_file_path)
        
        return StreamingResponse(open(audio_file_path, "rb"), media_type="audio/mpeg")
        
    except Exception as e:
        # Handle any errors that might occur and provide a fallback response
        print(f"Error in post_audio: {str(e)}")
        error_message = "There was an error processing your request. Let's continue the interview with the next question."
        error_audio_path = text_to_speech(error_message)
        background_tasks.add_task(delete_audio_file, error_audio_path)
        return StreamingResponse(open(error_audio_path, "rb"), media_type="audio/mpeg")

# New endpoint to track keyboard events
@app.post("/track-keyboard")
async def track_keyboard(event_data: Dict[str, Any], session_id: str = Query(..., description="Session ID")):
    """Track keyboard events and return warnings if any."""
    if session_id not in keyboard_trackers:
        keyboard_trackers[session_id] = KeyboardTracker()
    
    tracker = keyboard_trackers[session_id]
    warnings = tracker.track(event_data)
    
    if warnings:
        return JSONResponse(content={"warnings": warnings})
    else:
        return JSONResponse(content={"status": "ok"})


@app.post("/process-face")
async def process_face(frame_data: Dict[str, Any], session_id: str = Query(..., description="Session ID")):
    """Process webcam frame and detect faces and head movements."""
    # Only process if session exists
    if session_id not in face_detectors:
        face_detectors[session_id] = FaceDetector(
            min_detection_confidence=0.5,
            movement_threshold=0.1,
            history_size=10
        )
    
    detector = face_detectors[session_id]
    
    # Use a lightweight response when system is busy
    if frame_data.get("lightweight_check", False):
        return JSONResponse(content={"status": "ok", "lightweight": True})
    
    # Process the base64 image
    try:
        # Decode the base64 image
        image_bytes = base64.b64decode(frame_data.get("image", ""))
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Process the frame with the face detector
        results = detector.process_frame(frame)
        
        return JSONResponse(content=results)
    except Exception as e:
        print(f"Error in process_face: {str(e)}")
        return JSONResponse(content={
            "faces_count": 0, 
            "movement_detected": False, 
            "warnings": [f"Error processing frame: {str(e)}"]
        })


def delete_audio_file(file_path: str):
    """Delete the generated audio file after playing."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted audio file: {file_path}")
    except Exception as e:
        print(f"Error deleting file {file_path}: {e}")


@app.get("/clear")
async def clear_history(session_id: str = Query(..., description="Session ID")):
    """Clear chat history for a specific session."""
    redis_client.delete(f"session:{session_id}")
    
    # Clear keyboard tracker for the session
    if session_id in keyboard_trackers:
        del keyboard_trackers[session_id]
    
    # Clear face detector for the session
    if session_id in face_detectors:
        del face_detectors[session_id]
        
    return {"message": f"Chat history for session {session_id} has been cleared"}


async def transcribe_audio(file: UploadFile):
    """Convert speech to text using speech recognition."""
    audio_path = f"temp_audio_{uuid.uuid4().hex}.wav"
    try:
        with open(audio_path, 'wb') as buffer:
            buffer.write(await file.read())

        audio = AudioSegment.from_file(audio_path)
        audio.export(audio_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(audio_path) as source:
            audio_data = recognizer.record(source)

        try:
            transcript = recognizer.recognize_google(audio_data)
            return {"text": transcript}
        except sr.UnknownValueError:
            return {"text": "Could not understand the audio"}
        except sr.RequestError:
            return {"text": "Speech recognition request failed"}
    finally:
        # Clean up the temporary file
        if os.path.exists(audio_path):
            os.remove(audio_path)

def get_chat_response(user_message, session_id):
    """Generate AI response based on session chat history."""
    messages = load_messages(session_id) 
    
    # If user couldn't answer, add a prompt to continue the interview
    if user_message in ["I wasn't able to answer within the time limit.", "Sorry, I couldn't be heard clearly."]:
        messages.append({"role": "user", "content": user_message})
        # Add a system message to prompt the AI to continue with a new question
        messages.append({
            "role": "system", 
            "content": "The candidate couldn't answer in time. Continue the interview with a new question or follow-up. Be strict but encouraging."
        })
    else:
        messages.append({"role": "user", "content": user_message})

    conversation_prompt = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in messages])

    url = "http://127.0.0.1:11434/api/generate"  
    headers = {"Content-Type": "application/json"}
    data = {
        "model": "llama2",
        "prompt": conversation_prompt,
        "stream": False
    }

    start_time = time.time()
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response_time = time.time() - start_time

        if response.status_code == 200:
            try:
                gpt_response = response.json()
                if "response" in gpt_response:
                    parsed_response = gpt_response["response"]
                else:
                    parsed_response = "I understand you're having trouble with that question. Let's try a different topic. What can you tell me about React component lifecycle methods?"
            except (json.JSONDecodeError, KeyError):
                parsed_response = "Let's move on to another question. How would you optimize the performance of a React application?"
        else:
            parsed_response = "I see you're having difficulty. Let's switch to a different question. Can you explain the difference between props and state in React?"
    except requests.exceptions.RequestException:
        parsed_response = "Let's continue the interview with a new question. What's your experience with responsive design and CSS frameworks?"
        response_time = time.time() - start_time
    
    return parsed_response, response_time


def load_messages(session_id):
    """Retrieve chat history for a given session from Redis."""
    chat_history = redis_client.get(f"session:{session_id}")
    if chat_history:
        return json.loads(chat_history)  
    else:
        return [
            {"role": "system", "content": "You are interviewing the user for a front-end React developer position and his name is Sid. Ask short questions relevant to a junior-level developer. Keep responses under 30 words and be strict with grading. Please also don't tell the answer to the user until and unless he completely gives up on the answer and does not know anything. Also, ask him questions again and again, don't conclude the interview."}
        ]


def save_messages(session_id, user_message, gpt_response):
    """Save conversation to Redis under the session ID."""
    messages = load_messages(session_id)  
    messages.append({"role": "user", "content": user_message}) 
    messages.append({"role": "assistant", "content": gpt_response})  

    redis_client.set(f"session:{session_id}", json.dumps(messages))  # Save session conversation in Redis


def text_to_speech(text):
    """Convert AI response to speech and save as an audio file."""
    engine = pyttsx3.init()
    engine.setProperty('rate', 200)
    engine.setProperty('volume', 1.0)

    audio_path = f"response_{uuid.uuid4().hex}.mp3"  
    engine.save_to_file(text, audio_path)
    engine.runAndWait()

    return audio_path