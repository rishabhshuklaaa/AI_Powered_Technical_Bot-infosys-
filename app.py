from flask import Flask, request, jsonify
from flask_cors import CORS  # Import flask_cors
from dotenv import load_dotenv
import os
from concurrent.futures import ThreadPoolExecutor
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import PromptTemplate
import json
from technical_councellor_agent import TechnicalSupportAgent  # Assuming 'TechnicalSupportAgent' is defined in 'wsgi.py'

load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for the entire app
agent = TechnicalSupportAgent()  # Properly instantiate the agent

# MultiSupportAgent Class
class MultiSupportAgent:
    def __init__(self, model: str = None, api_key: str = None, temperature: float = 0.6):
        self.llm = self._initialize_llm(
            model or os.getenv("YOUR_MODEL_NAME"),
            api_key or os.getenv("YOUR_API_KEY"),
            temperature
        )
        self.memory = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.initialize_prompts()

    def initialize_prompts(self):
        self.prompts = {
            'technical_support': """
                You are a technical support assistant. Respond intelligently and politely to the user's issue.
                Here are the details:
                User Details: {user_details}
                Conversation History: {conversation_history}
                User's Message: {user_message}
                Provide a helpful and specific response.
            """,
            'billing': """
                You are a billing assistant. Respond intelligently to questions about billing or payments.
                Here are the details:
                User Details: {user_details}
                Conversation History: {conversation_history}
                User's Message: {user_message}
                Provide a clear and concise response.
            """,
            'service_request': """
                You are a customer service assistant. Respond intelligently to questions about new connections or service upgrades.
                Here are the details:
                User Details: {user_details}
                Conversation History: {conversation_history}
                User's Message: {user_message}
                Provide an informative response.
            """,
            'account_management': """
                You are an account management assistant. Help the user with account-related issues.
                Here are the details:
                User Details: {user_details}
                Conversation History: {conversation_history}
                User's Message: {user_message}
                Provide a step-by-step response.
            """,
            'general_queries': """
                You are a general customer support assistant. Respond to the user's queries.
                Here are the details:
                User Details: {user_details}
                Conversation History: {conversation_history}
                User's Message: {user_message}
                Provide an engaging and helpful response.
            """
        }

    @staticmethod
    def _initialize_llm(model: str, api_key: str, temperature: float) -> ChatGoogleGenerativeAI:
        if not model or not api_key:
            raise ValueError("Model and API key must be provided")
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            api_key=api_key
        )

    def get_user_memory(self, user_id: str) -> ConversationBufferMemory:
        if user_id not in self.memory:
            self.memory[user_id] = ConversationBufferMemory(
                memory_key=f"conversation_history_{user_id}",
                return_messages=True
            )
        return self.memory[user_id]

    def _get_conversation_history(self, user_id: str) -> str:
        memory = self.get_user_memory(user_id)
        history = memory.load_memory_variables({})
        return "\n".join(history.get(f"conversation_history_{user_id}", []))

    def _categorize_query(self, query: str) -> str:
        if any(keyword in query.lower() for keyword in ["wi-fi", "internet", "connectivity"]):
            return "technical_support"
        elif any(keyword in query.lower() for keyword in ["bill", "payment", "balance"]):
            return "billing"
        elif any(keyword in query.lower() for keyword in ["new connection", "upgrade", "install"]):
            return "service_request"
        elif any(keyword in query.lower() for keyword in ["password", "account"]):
            return "account_management"
        else:
            return "general_queries"

    def get_prompt_template(self, category: str) -> PromptTemplate:
        return PromptTemplate(
            input_variables=["user_details", "conversation_history", "user_message"],
            template=self.prompts.get(category, self.prompts['general_queries'])
        )

    def get_support_response(self, user_details: dict, user_message: str, user_id: str) -> dict:
        try:
            # Categorize query
            category = self._categorize_query(user_message)
            user_memory = self.get_user_memory(user_id)
            conversation_history = self._get_conversation_history(user_id)

            inputs = {
                "user_details": json.dumps(user_details, indent=2),
                "conversation_history": conversation_history,
                "user_message": user_message,
            }

            prompt_template = self.get_prompt_template(category)
            formatted_prompt = prompt_template.format(**inputs)

            response = self.llm.predict(formatted_prompt)
            user_memory.save_context({"input": user_message}, {"output": response})
            return {"response": response, "category": category}

        except Exception as e:
            return {"error": str(e)}

# Required fields for request validation
REQUIRED_REQUEST_FIELDS = ['user_id', 'user_details', 'user_message']
REQUIRED_USER_FIELDS = [
    'user_id',
    'user_details'
]

@app.route('/support', methods=['POST'])
def support_endpoint():
    """
    REST API Endpoint for handling various queries.
    """
    try:
        # Parse JSON from the request
        data = request.json
        user_id = data.get('user_id')
        user_details = data.get('user_details', {})
        user_message = data.get('user_message')

        if not user_id or not user_message:
            return jsonify({"error": "user_id and user_message are required"}), 400

        # Check if the query is asking for the customer care number
        if "customer care number" in user_message.lower() or "contact number" in user_message.lower():
            return jsonify({
                "response": "Thank you for reaching out! You can contact Airtel customer care by visiting our support page: https://www.airtel.in/support"
            })
        
        # Check if the query is asking to schedule a technical visit
        if "schedule technical visit" in user_message.lower():
            return jsonify({
                "response": "Thank you for your request! To schedule a technical visit, please visit our support page: https://www.airtel.in/support"
            })

        # Get the response from the agent for other queries
        response = agent.get_support_response(user_details, user_message, user_id)

        # Return the response
        if "error" in response:
            return jsonify({"error": response["error"]}), 500

        return jsonify(response)

    except Exception as e:
        # Handle the case when there's a server issue or error
        return jsonify({
            'response': "It seems there was an issue processing your request. Please visit our support page for assistance: https://www.airtel.in/support",
            'error': str(e)  # Optional: Error details for debugging
        }), 500





# Run the Flask App
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
