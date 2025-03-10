from fastapi import FastAPI, UploadFile, Query, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
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

@app.get("/start-session")
async def start_session():
    """Create a new session and return a unique session_id."""
    session_id = str(uuid.uuid4())  # Generate a unique session IDinitial_prompt = [
    initial_prompt = [{
        "role": "system",
        "content": "You are interviewing the user for a front-end React developer position and his name is Sid. Ask short questions relevant to a junior-level developer. Keep responses under 30 words and be strict with grading. Please also don’t tell the answer to the user until and unless he completely gives up on the answer and does not know anything. Also, ask him questions again and again, don't conclude the interview.Please be super strict with the interview and grading"
    }
]
    redis_client.set(f"session:{session_id}", json.dumps(initial_prompt))
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
        if is_time_completed:
            user_message = "Sorry, was not able to answer within the time."
            chat_response, response_time = get_chat_response(user_message, session_id)
            save_messages(session_id, user_message, chat_response)
            audio_file_path = text_to_speech(chat_response)
        else:
            if not file:
                # Handle case when no file is provided but isTimeCompleted is False
                user_message = "Sorry, was not able to answer within the time."
                chat_response, response_time = get_chat_response(user_message, session_id)
                save_messages(session_id, user_message, chat_response)
                audio_file_path = text_to_speech(chat_response)
            else:
                user_message = await transcribe_audio(file)
                chat_response, response_time = get_chat_response(user_message["text"], session_id)
                save_messages(session_id, user_message["text"], chat_response)
                audio_file_path = text_to_speech(chat_response)
        
        # Schedule file deletion after sending response
        background_tasks.add_task(delete_audio_file, audio_file_path)
        return StreamingResponse(open(audio_file_path, "rb"), media_type="audio/mpeg")
        
    except Exception as e:
        # Handle any errors that might occur and provide a fallback response
        print(f"Error in post_audio: {str(e)}")
        error_message = "There was an error processing your request."
        error_audio_path = text_to_speech(error_message)
        background_tasks.add_task(delete_audio_file, error_audio_path)
        return StreamingResponse(open(error_audio_path, "rb"), media_type="audio/mpeg")


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
    return {"message": f"Chat history for session {session_id} has been cleared"}


async def transcribe_audio(file: UploadFile):
    """Convert speech to text using speech recognition."""
    audio_path = "temp_audio.wav"
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


def get_chat_response(user_message, session_id):
    """Generate AI response based on session chat history."""
    messages = load_messages(session_id) 
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
    response = requests.post(url, headers=headers, json=data)
    response_time = time.time() - start_time

    try:
        gpt_response = response.json()
        if "response" in gpt_response:
            parsed_response = gpt_response["response"]
    except (json.JSONDecodeError, KeyError):
        parsed_response = "Error processing response from the AI."

    # print(f"Ollama response time: {response_time:.2f} seconds")

    return parsed_response, response_time


def load_messages(session_id):
    """Retrieve chat history for a given session from Redis."""
    chat_history = redis_client.get(f"session:{session_id}")
    if chat_history:
        return json.loads(chat_history)  
    else:
        return [
            {"role": "system", "content": "You are interviewing the user for a front-end React developer position and his name is Sid. Ask short questions relevant to a junior-level developer. Keep responses under 30 words and be strict with grading. Please also don’t tell the answer to the user until and unless he completely gives up on the answer and does not know anything. Also, ask him questions again and again, don't conclude the interview."}
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
