import io
import os
import copy
import requests
from flask import Flask, jsonify, request
import json

import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from PIL import Image

app = Flask(__name__)

# API KEY for genai
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

# Access token for your WhatsApp business account app
whatsapp_token = os.environ.get("WHATSAPP_TOKEN")

# Verify Token defined when configuring the webhook
verify_token = os.environ.get("VERIFY_TOKEN")

# Message log dictionary to enable conversation over multiple messages
message_log_dict = {}
# Current feature from user
current_feature = {}

# language for speech to text recoginition
# TODO: detect this automatically based on the user's language
LANGUGAGE = "pt-BR"

# feature const
SPLIT_BILLS = "SPLIT_BILLS"
COLLECT_DEBT = "COLLECT_DEBT"
LIST_DEBT = "LIST_DEBT"

image_url = 'https://picsum.photos/200/300'

# Sets homepage endpoint and welcome message
@app.route("/", methods=["GET"])
def home():
    response = requests.get(image_url)
    image = Image.open(io.BytesIO(response.content))
    message = ["O que tem na imagem?", image]
    
    teste_model = genai.GenerativeModel('gemini-1.5-flash')
    response = teste_model.generate_content(message)
    print('TESTE')
    print(response.text)
    return response.text


if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, port=8001)