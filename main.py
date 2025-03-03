from fastapi import FastAPI, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import speech_recognition as sr
from pydub import AudioSegment
from dotenv import load_dotenv
import pyttsx3
import os
import json
import requests
import time

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

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

@app.post("/talk")
async def post_audio(file: UploadFile):
    user_message = await transcribe_audio(file)
    print(f"DEBUG: Transcribed audio: {user_message['text']}")

    chat_response, response_time = get_chat_response(user_message["text"])
    print(f"DEBUG: Groq Response: {chat_response}")

    save_messages(user_message["text"], chat_response)  # Save updated chat history

    audio_file_path = text_to_speech(chat_response)

    return StreamingResponse(open(audio_file_path, "rb"), media_type="audio/mpeg")

@app.get("/clear")
async def clear_history():
    file = 'database.json'
    open(file, 'w').close()
    return {"message": "Chat history has been cleared"}

async def transcribe_audio(file: UploadFile):
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

def get_chat_response(user_message):
    messages = load_messages()
    messages.append({"role": "user", "content": user_message})

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama3-8b-8192",
        "messages": messages
    }

    start_time = time.time()
    response = requests.post(url, headers=headers, json=data)
    response_time = time.time() - start_time

    parsed_gpt_response = "Error processing response from the AI."  # Default fallback

    try:
        gpt_response = response.json()
        if "choices" in gpt_response and gpt_response["choices"]:
            parsed_gpt_response = gpt_response['choices'][0]['message']['content']
    except (json.JSONDecodeError, KeyError):
        parsed_gpt_response = "Error processing response from the AI."

    save_messages(user_message, parsed_gpt_response)
    print(f"Groq response time: {response_time:.2f} seconds")
    
    return parsed_gpt_response, response_time  # Ensure always two values returned


def load_messages():
    file = 'database.json'
    if os.path.exists(file) and os.stat(file).st_size > 0:
        with open(file) as db_file:
            return json.load(db_file)  # Load full history
    else:
        return [{"role": "system", "content": "You are interviewing the user for a front-end React developer position and his name is Sid. Ask short questions relevant to a junior-level developer. Keep responses under 30 words and be strict with grading."}]

def save_messages(user_message, gpt_response):
    file = 'database.json'
    messages = load_messages()  # Load existing history
    messages.append({"role": "user", "content": user_message})  # Append new user input
    messages.append({"role": "assistant", "content": gpt_response})  # Append AI response
    with open(file, 'w') as f:
        json.dump(messages, f)  # Save full conversation history

def text_to_speech(text):
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)  # Adjust speed (default ~200)
    engine.setProperty('volume', 1.0)  # Max volume
    audio_path = "response_audio.mp3"

    engine.save_to_file(text, audio_path)
    engine.runAndWait()

    return audio_path
