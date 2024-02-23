from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import os
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import re
from fuzzywuzzy import process

app = Flask(__name__)

# Replace 'your_openai_api_key' with your actual OpenAI API key

# Global variable to store the extracted text from the docx file
DOCX_FILE_PATH = 'knowledge.docx'

# Function to extract text from the .docx file
from docx import Document

def extract_text_from_docx(file_path):
    doc = Document(file_path)
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    
    extracted_text = '\n'.join(full_text)

    # Print the entire extracted text or a part of it for debugging
    print("Extracted text:", extracted_text[:1000])  # Print the first 1000 characters

    return extracted_text

# Read the .docx file and store its content
docx_text = extract_text_from_docx(DOCX_FILE_PATH)

# Function to update the docx_text
def update_docx_text():
    global docx_text
    docx_text = extract_text_from_docx(DOCX_FILE_PATH)
    print("Document text updated")  # Optional, for logging

# Bot's role and instructions
bot_instructions = """
You are an assistant for guests staying in AirBnb's who have simple questions regarding their stay.

In general, your role is broken up as follows:

- You have an important role to play in guest's happiness and satisfaction when it comes to their stay
- Guest's will rely on you to answer common queries unique to which property they're staying at
- Where possible kindly advise the guest's as to how to solve their query/problem
- When answering guests keep the answers short and to the point, you do not need to repeat the address back to the guest
- If a guest has already provided you with the address and passcode there is no need to ask for it again
- If the answer to a question is not in the knowledge file, please let the guest know you are not able to answer the question
- You should use simple, non-technical language as often as possible to make it easy for guest's to understand exactly what is being said
"""

conversation_states = {}

def get_ai_response(question, contextual_info):
    try:
        combined_context = bot_instructions + "\n" + contextual_info
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": combined_context},
                {"role": "user", "content": question}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return str(e)
    
@app.route('/') 
def index():
   return render_template('main.html')

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    session_id = data.get('session_id')  # Unique identifier for each user/session
    user_input = data.get('input', '')

    # Debug print to check session state and user input
    print("Session ID:", session_id, "Current Stage:", conversation_states.get(session_id, {}).get("stage"), "User Input:", user_input)

    if session_id not in conversation_states:
        conversation_states[session_id] = {"stage": "greeting"}
        return jsonify({'response': 'Hello! Welcome to BnBuddy, your virtual assistant! Please provide the address of the property you are staying at.'})

    if conversation_states[session_id]["stage"] == "greeting":
        valid, contextual_info = is_valid_address(user_input)
        if valid:
            conversation_states[session_id] = {
                "stage": "awaiting_security_pass",
                "address": user_input,
                "context": contextual_info  # Store contextual information
            }
            return jsonify({'response': 'Address verified. Please provide your security pass.'})
        else:
            return jsonify({'response': 'The address provided does not match our records. Please try again.'})

    elif conversation_states[session_id]["stage"] == "awaiting_security_pass":
        # Here we should validate the security pass instead of re-checking the address
        if is_valid_security_pass(user_input):
            conversation_states[session_id]["stage"] = "ready_for_questions"
            return jsonify({'response': 'Security pass verified. How can I assist you with your stay today?'})
        else:
            return jsonify({'response': 'Invalid security pass. Please try again.'})

    elif conversation_states[session_id]["stage"] == "ready_for_questions":
    # Get the contextual information related to the property address
        contextual_info = conversation_states[session_id].get("context", "")

    # Debug print to check what contextual information is being used
        print("Contextual Info for response:", contextual_info)
    
        # Get the AI response with the contextual information
        answer = get_ai_response(user_input, contextual_info)

         # Debug print to check the AI's response
        print("AI Response:", answer)

    
        return jsonify({'response': answer})

    else:
        return jsonify({'error': 'Something went wrong.'}), 500


from fuzzywuzzy import process

def is_valid_address(address):
    pattern = r"Address:\s*([^\n]+)\nSecurity pass:"
    matches = re.findall(pattern, docx_text, re.IGNORECASE)
    print("Extracted Addresses:", matches)  # Debug print
    # Use FuzzyWuzzy to find the closest match to the given address
    result = process.extractOne(address.lower(), [match.lower() for match in matches])
    print("Fuzzy Match Result:", result)  # Debug print
    
    if result:
        closest_match, score = result
        print("Closest Match", closest_match, "Score:", score)

        if score > 75:  # Assuming a threshold of 75% for a "close enough" match
            # Extract and return additional contextual information related to this address
            contextual_info = extract_contextual_info(closest_match)
            return True, contextual_info
        
    else:
        print("No close match found for address:", address)
    return False, None

# Function to extract contextual information for a given address
def extract_contextual_info(address):
    # Pattern to match the address block
    pattern = re.compile(r"Address:\s*" + re.escape(address) + r".*?(?=Address:|$)", re.DOTALL | re.IGNORECASE)

    match = pattern.search(docx_text)
    if match:
        # Extract the text block corresponding to the address
        address_block = match.group(0)
        # Further processing to extract specific details from the address block
        # Depending on how the information is structured, you might use additional parsing here
        return address_block
    return None

def is_valid_security_pass(security_pass):
    pattern = r"Security Pass:\s*([^\n]+)"
    matches = re.findall(pattern, docx_text, re.IGNORECASE)
    return security_pass.lower() in (match.lower() for match in matches)
    

if __name__ == '__main__':
    # Setup the background scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=update_docx_text, trigger="interval", minutes=10)
    scheduler.start()

    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

    app.run(debug=True)