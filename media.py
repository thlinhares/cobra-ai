import os
import io
import requests
import pydub
import soundfile as sf
import speech_recognition as sr
import base64
from PIL import Image

# Access token for your WhatsApp business account app
whatsapp_token = os.environ.get("WHATSAPP_TOKEN")

# get the media url from the media id
def get_media_url(media_id):
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
    }
    url = f"https://graph.facebook.com/v16.0/{media_id}/"
    response = requests.get(url, headers=headers)
    print(f"media id response: {response.json()}")
    return response.json()["url"]


# download the media file from the media url
def download_media_file(media_url):
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
    }
    response = requests.get(media_url, headers=headers)
    print(f"first 10 digits of the media file: {response.content[:10]}")
    return response.content


# convert ogg audio bytes to audio data which speechrecognition library can process
def convert_audio_bytes(audio_bytes):
    ogg_audio = pydub.AudioSegment.from_ogg(io.BytesIO(audio_bytes))
    ogg_audio = ogg_audio.set_sample_width(4)
    wav_bytes = ogg_audio.export(format="wav").read()
    audio_data, sample_rate = sf.read(io.BytesIO(wav_bytes), dtype="int32")
    sample_width = audio_data.dtype.itemsize
    print(f"audio sample_rate:{sample_rate}, sample_width:{sample_width}")
    audio = sr.AudioData(audio_data, sample_rate, sample_width)
    return audio


# run speech recognition on the audio data
def recognize_audio(audio_bytes):
    recognizer = sr.Recognizer()
    audio_text = recognizer.recognize_google(audio_bytes, language=LANGUGAGE)
    return audio_text


# handle audio messages
def handle_audio_message(audio_id):
    audio_url = get_media_url(audio_id)
    audio_bytes = download_media_file(audio_url)
    audio_data = convert_audio_bytes(audio_bytes)
    audio_text = recognize_audio(audio_data)
    message = (
        "Please summarize the following message in its original language "
        f"as a list of bullet-points: {audio_text}"
    )
    return audio_text #message

# handle image messages
def handle_image_message(image_id):
    image_url = get_media_url(image_id)
    image_bytes = download_media_file(image_url)
    return Image.open(io.BytesIO(image_bytes))


