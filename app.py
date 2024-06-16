import io
import os
import copy
import requests
from flask import Flask, jsonify, request
import json

import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

app = Flask(__name__)

# API KEY for genai
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

# Access token for your WhatsApp business account app
whatsapp_token = os.environ.get("WHATSAPP_TOKEN")

# Verify Token defined when configuring the webhook
verify_token = os.environ.get("VERIFY_TOKEN")

# Message log dictionary to enable conversation over multiple messages
message_log_dict = {}

# language for speech to text recoginition
# TODO: detect this automatically based on the user's language
LANGUGAGE = "pt-BR"

# feature const
SPLIT_BILLS = "SPLIT_BILLS"
COLLECT_DEBT = "COLLECT_DEBT"
LIST_DEBT = "LIST_DEBT"

initial_model = [
    SystemMessage(content=[
        'Você é um assistente virtual chamado CobraAI. Suas principais habilidades é ajudar as pessoas a realizar tarefas financeiras.',
        'Estão disponivel as seguintes funcionalidades que posso fazer no momento: SPLIT_BILLS - Divir conta entre amigos; COLLECT_DEBT - Cobrar debitos atrasados; LIST_DEBT - Listar cobranças;',
        'Você deve responder utilizando o schema: { "message":str, "feature":str}',
        '"message" deve conter sua resposa e "feature" deve conter a funcionalidade escoliha pelo usuario, informe "" caso nenhuma das opções.',
        'Voçê não deve responder sobre qualquer outro assunto.'
    ])
]

initial_feature_split_bills = [
    SystemMessage(content=[
        'Você é um assistente virtual chamado CobraAI e esta ajudando o usuario a dividir uma conta com os amigos.',
        'Você deve identificar todos os itens consumidos no cupon fiscal e realizar a soma dos valores.',
        'Após identificaçao dos itens, você deve dividir a conta entre os amigos, informando o valor que cada um deve pagar',
        'Você deve responder utilizando o schema: { "message":str, "feature":"SPLIT_BILLS"}',
        '"message" deve conter sua resposa e "feature" deve conter a funcionalidade deve ser SPLIT_BILLS',
        'Voçê não deve responder sobre qualquer outro assunto.'
    ])
]

# send the response as a WhatsApp message back to the user
def send_whatsapp_message(body, message):
    value = body["entry"][0]["changes"][0]["value"]
    phone_number_id = value["metadata"]["phone_number_id"]
    from_number = value["messages"][0]["from"]
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json",
    }
    url = "https://graph.facebook.com/v15.0/" + phone_number_id + "/messages"
    data = {
        "messaging_product": "whatsapp",
        "to": from_number,
        "type": "text",
        "text": {"body": message},
    }
    response = requests.post(url, json=data, headers=headers)
    print(f"whatsapp message response: {response.json()}")
    response.raise_for_status()


# create a message log for each phone number and return the current message log
def update_message_log(message, phone_number, role):
    if phone_number not in message_log_dict:
        message_log_dict[phone_number] = copy.copy(initial_model)
    if role == "user":
        message_log = HumanMessage(content=message)
    elif role == "assistant":
        message_log = AIMessage(content=message)
    message_log_dict[phone_number].append(message_log)
    return message_log_dict[phone_number]
  
# remove last message from log if OpenAI request fails
def remove_last_message_from_log(phone_number):
    message_log_dict[phone_number].pop()

# make message feature
def make_message_feature(feature, from_number):
    if feature == SPLIT_BILLS:
        message_log_dict[from_number] = initial_feature_split_bills
        message_feature = "Ok, você pode começar enviando a foto do cupon fiscal."
        update_message_log(message_feature, from_number, "assistant")
    elif feature == COLLECT_DEBT:
        message_log_dict[from_number] = copy.copy(initial_model)
        message_feature = "Desculpa, ainda estou aprendendo a realizar cobranças..."
    elif feature == LIST_DEBT:
        message_log_dict[from_number] = copy.copy(initial_model)
        message_feature = "Aqui esta as suas cobranças cadastradas, posso ajudar em algo mais?"
    else:
        message_feature = "Ops... erro!"
    
    return message_feature
    
# make request to OpenAI
def make_openai_request(message, from_number):
    try:
        llm = ChatGoogleGenerativeAI(model='gemini-1.5-flash',
                                    generation_config={"response_mime_type": "application/json"})
        print(f"LIST 1: {message_log_dict}")
        message_log = update_message_log(message, from_number, "user")
        print(f"LIST 2: {message_log_dict}")
        
        print(f"Request AI: {message_log}")
        response = llm.invoke(message_log)
        print(f"Response AI: {response.content}")
        response_json = json.loads(response.content)
        update_message_log(response_json["message"], from_number, "assistant")
    except Exception as e:
        print(f"openai error: {e}")
        response_json = {'message': "Sorry, the AI API is currently overloaded or offline. Please try again later.", 'feature': ''}
        remove_last_message_from_log(from_number)
    return response_json


# handle WhatsApp messages of different type
def handle_whatsapp_message(body):
    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    if message["type"] == "text":
        message_body = message["text"]["body"]
    elif message["type"] == "audio":
        audio_id = message["audio"]["id"]
        message_body = handle_audio_message(audio_id)
    
    response = make_openai_request(message_body, message["from"])
    msg = response["message"]
    if response["feature"] != '':
      msg = make_message_feature(response["feature"], message["from"])
    
    send_whatsapp_message(body, msg)
    

# handle incoming webhook messages
def handle_message(request):
    # Parse Request body in json format
    body = request.get_json()

    try:
        # info on WhatsApp text message payload:
        # https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples#text-messages
        if body.get("object"):
            if (
                body.get("entry")
                and body["entry"][0].get("changes")
                and body["entry"][0]["changes"][0].get("value")
                and body["entry"][0]["changes"][0]["value"].get("messages")
                and body["entry"][0]["changes"][0]["value"]["messages"][0]
            ):
                print(f"request body: {body}")
                handle_whatsapp_message(body)
            return jsonify({"status": "ok"}), 200
        else:
            # if the request is not a WhatsApp API event, return an error
            return (
                jsonify({"status": "error", "message": "Not a WhatsApp API event"}),
                404,
            )
    # catch all other errors and return an internal server error
    except Exception as e:
        print(f"unknown error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Required webhook verifictaion for WhatsApp
# info on verification request payload:
# https://developers.facebook.com/docs/graph-api/webhooks/getting-started#verification-requests
def verify(request):
    # Parse params from the webhook verification request
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    # Check if a token and mode were sent
    if mode and token:
        # Check the mode and token sent are correct
        if mode == "subscribe" and token == verify_token:
            # Respond with 200 OK and challenge token from the request
            print("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            # Responds with '403 Forbidden' if verify tokens do not match
            print("VERIFICATION_FAILED")
            return jsonify({"status": "error", "message": "Verification failed"}), 403
    else:
        # Responds with '400 Bad Request' if verify tokens do not match
        print("MISSING_PARAMETER")
        return jsonify({"status": "error", "message": "Missing parameters"}), 400


# Sets homepage endpoint and welcome message
@app.route("/", methods=["GET"])
def home():
    return f"WhatsApp OpenAI Webhook is listening! {os.environ["OPENAI_API_KEY"]}"


# Accepts POST and GET requests at /webhook endpoint
@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    if request.method == "GET":
        return verify(request)
    elif request.method == "POST":
        return handle_message(request)


# Route to reset message log
@app.route("/reset", methods=["GET"])
def reset():
    global message_log_dict
    message_log_dict = {}
    return "Message log resetted!"


if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, port=8001)
