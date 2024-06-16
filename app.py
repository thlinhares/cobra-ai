import io
import os

import requests
from flask import Flask, jsonify, request
import json


app = Flask(__name__)

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

initial_roles = [
    {"role": "system", "content": "Você é um assistente virtual chamado CobraAI. Suas principais habilidades é ajudar as pessoas a realizar tarefas financeiras."},
    {"role": "system", "content": "Estão disponivel as seguintes funcionalidades que posso fazer no momento: SPLIT_BILLS - Divir conta entre amigos; COLLECT_DEBT - Cobrar debitos atrasados; LIST_DEBT - Listar cobranças;"},
    {"role": "system", "content": "Voçê não deve responder sobre qualquer outro assunto."},
    {"role": "system", "content": "Você deve responder em formato json contendo duas propriedades do tipo string: 'message' deve conter sua respota tem texto; 'feature' deve conter a funcionalidade escolilhada pelo usuario, None caso nenhuma das opções;"}
]

initial_feature_collect_debt = [
    {"role": "system", "content": "Você é um assistente virtual chamado CobraAI e deve montar uma mensagem de cobrança para ser enviada."},
    {"role": "system", "content": "Os dados do devedor e da cobrança sera informando pelo usuario em seguida."},
    {"role": "system", "content": "Voçê não deve responder sobre qualquer outro assunto."},
    {"role": "system", "content": "Você deve responder em formato json contendo duas propriedades do tipo string: 'message' deve conter sua respota tem texto; 'feature' deve conter a funcionalidade COLLECT_DEBT;"}
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
    initial_log = {
        "role": "system",
        "content": ("Você é um assistente virtual chamado CobraAI."
                    "Suas principais habilidades é ajudar as pessoas a realizar tarefas financeiras."
                    "Abaixo esta descrito as funcionalidades disponivel que posso fazer no momento:"
                    "SPLIT_BILLS: Divir conta entre amigos;"
                    "COLLECT_DEBT: Cobrar debitos atrasados;"
                    "LIST_DEBT: Listar cobranças;"
                    "Voçê não deve responder sobre qualquer outro assunto."
                    "Você deve responder em formato json contendo duas propriedades do tipo string: 'message' e 'feature'."
                    "'message' deve conter sua respota tem texto."
                    "'feature' deve conter a funcionalidade escolilhada pelo usuario, null caso nenhuma das opções."
                   )
    }
    if phone_number not in message_log_dict:
        message_log_dict[phone_number] = initial_roles #[initial_log]
    message_log = {"role": role, "content": message}
    message_log_dict[phone_number].append(message_log)
    return message_log_dict[phone_number]


# reset message from log
def reset_message_from_log(phone_number):
    message_log_dict[phone_number] = []
  
# remove last message from log if OpenAI request fails
def remove_last_message_from_log(phone_number):
    message_log_dict[phone_number].pop()

# make message feature
def make_message_feature(feature, from_number):
    message_feature = "Ops... erro!"
    if feature == SPLIT_BILLS:
      message_feature = "Desculpa, ainda estou aprendendo a dividir contas entre amigos."
    elif feature == COLLECT_DEBT:
      reset_message_from_log(from_number)
      message_log_dict[phone_number] = initial_feature_collect_debt
      message_feature = "Informe os dados da cobrança: \n Nome devedor, telefone, valor e data da cobrança."
    elif feature == LIST_DEBT:
      message_feature = "Vou buscar os dados de cobranças cadastrados, um momento por favor!"
    
    return message_feature
    
# make request to OpenAI
def make_openai_request(message, from_number):
    try:
        message_log = update_message_log(message, from_number, "user")
        
        url = "https://api.awanllm.com/v1/chat/completions"
        payload = json.dumps({
          "model": "Awanllm-Llama-3-8B-Dolfin",
          "messages": message_log,
          "repetition_penalty": 1.1,
          "temperature": 0.7,
          "top_p": 0.9,
          "top_k": 40,
          "max_tokens": 1024,
          "stream": False
        })
        headers = {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + os.getenv("OPENAI_API_KEY")
        }
        print(f"Request AI: {payload}")
        response = requests.request("POST", url, headers=headers, data=payload)
        print(response)
        response_json = json.loads(response.json()["choices"][0]["message"]["content"])
        print(f"Response JSON AI: {response_json}")
        update_message_log(response_json["message"], from_number, "assistant")
    except Exception as e:
        print(f"openai error: {e}")
        response_json = {'message': "Sorry, the OpenAI API is currently overloaded or offline. Please try again later.", 'feature': None}
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
    if response["feature"] != None:
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
    return "WhatsApp OpenAI Webhook is listening!"


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
    app.run(debug=False, use_reloader=False)
