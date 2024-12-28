import os
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
from functools import lru_cache
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import PromptTemplate
from langsmith import traceable

load_dotenv()

class TechnicalSupportAgent:
    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, temperature: float = 0.6):
        self.llm = self._initialize_llm(
            model or os.getenv("YOUR_MODEL_NAME"),
            api_key or os.getenv("YOUR_API_KEY"),
            temperature
        )
        self.memory: Dict[str, ConversationBufferMemory] = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.initialize_prompts()

    def initialize_prompts(self):
        self.prompts = {
            'technical_support': """
                You are a technical support assistant. Respond intelligently and politely to the user's issue.
                Here are the details:
                
                User Details:
                {user_details}
                
                Conversation History:
                {conversation_history}
                
                User's Message:
                {user_message}
                
                Provide a helpful and specific response.
            """,
            'billing': """
                You are a billing assistant. Respond intelligently to questions about billing or payments.
                Here are the details:
                
                User Details:
                {user_details}
                
                Conversation History:
                {conversation_history}
                
                User's Message:
                {user_message}
                
                Provide a clear and concise response.
            """,
            'service_request': """
                You are a customer service assistant. Respond intelligently to questions about new connections or service upgrades.
                Here are the details:
                
                User Details:
                {user_details}
                
                Conversation History:
                {conversation_history}
                
                User's Message:
                {user_message}
                
                Provide an informative response.
            """,
            'account_management': """
                You are an account management assistant. Help the user with account-related issues.
                Here are the details:
                
                User Details:
                {user_details}
                
                Conversation History:
                {conversation_history}
                
                User's Message:
                {user_message}
                
                Provide a step-by-step response.
            """,
            'general_queries': """
                You are a general customer support assistant. Respond to the user's queries.
                Here are the details:
                
                User Details:
                {user_details}
                
                Conversation History:
                {conversation_history}
                
                User's Message:
                {user_message}
                
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

    def _get_conversation_history(self, user_id: str) -> List[Any]:
        return self.get_user_memory(user_id).load_memory_variables({}).get(
            f'conversation_history_{user_id}', []
        )

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

    def _prepare_support_inputs(self, user_details: Dict[str, Any], user_message: str, conversation_history: List[Any]) -> Dict[str, Any]:
        conversation_summary = [
            f"{msg.type}: {msg.content}" if hasattr(msg, 'content')
            else f"{msg.get('type', 'Unknown')}: {msg.get('content', '')}" if isinstance(msg, dict)
            else str(msg)
            for msg in conversation_history
        ]
        return {
            'user_details': json.dumps(user_details, indent=2),
            'conversation_history': "\n".join(conversation_summary),
            'user_message': user_message,
        }

    def get_prompt_template(self, category: str) -> PromptTemplate:
        return PromptTemplate(
            input_variables=["user_details", "conversation_history", "user_message"],
            template=self.prompts.get(category)
        )

    @traceable(project_name="technical-support-agent")
    def get_support_response(self, user_details: Dict[str, Any], user_message: str, user_id: str) -> Dict[str, Any]:
        try:
            # Handle call or technical visit request
            if any(keyword in user_message.lower() for keyword in ["schedule call", "visit", "setup connection"]):
                return self.schedule_visit_or_call(user_message)

            # Handle new connection request and collect further details
            if "new connection" in user_message.lower():
                return self.handle_new_connection(user_details, user_message)

            # Handle feedback
            if "thank you" in user_message.lower() or "exit" in user_message.lower() or "okay bye" in user_message.lower():
                return self.ask_for_feedback(user_message)

            # Check if user gave feedback
            if user_message in ['1', '2', '3', '4', '5']:
                return self.handle_feedback(user_message)

            # Check for exit phrases like "bye" or "thank you" to end the conversation
            if "bye" in user_message.lower() or "thank you" in user_message.lower() or "okay bye" in user_message.lower():
                return self.handle_exit()

            # Categorize the query
            category = self._categorize_query(user_message)
            user_memory = self.get_user_memory(user_id)
            conversation_history = self._get_conversation_history(user_id)

            inputs = self._prepare_support_inputs(user_details, user_message, conversation_history)
            prompt_template = self.get_prompt_template(category)
            formatted_prompt = prompt_template.format(**inputs)

            response = self.llm.predict(formatted_prompt)

            user_memory.save_context({"input": user_message}, {"output": response})

            # Handle unresolved technical issues
            if "technical issue" in user_message.lower() and "resolved" not in user_message.lower():
                return self.ask_for_engineer_visit()

            return {'response': response}

        except Exception as e:
            return {'error': f"An error occurred: {str(e)}"}

    def ask_for_feedback(self, previous_response: str) -> Dict[str, Any]:
        # Asking for feedback on a scale of 1 to 5
        return {
            'response': f"Thank you for your message! Please rate our service on a scale of 1 to 5."
        }

    def handle_feedback(self, feedback: str) -> Dict[str, Any]:
        # Handle feedback and end the conversation or move to the next step
        if feedback in ['1', '2', '3', '4', '5']:
            if int(feedback) > 3:
                return{
                    'response': f"Thank you for your feedback! You rated our service as {feedback}, Excellent!"
                }
            elif int(feedback)<3:
                return{
                    'response': f"Thank you for your feedback! You rated our service as {feedback}. Please provide suggestions for improvement."
                }
            else:
                return{
                     'response': f"Thank you for your feedback! You rated our service as {feedback}, Satisfactory."
                }
        else:
            return{
                'response': "It seems you provided an invalid rating. Please rate our service on a scale of 1 to 5."
            }
            
        #     return {
        #         'response': f"Thank you for your feedback! You rated our service as {feedback}. satisfactory!"
        #     }
        # else:
        #     return {
        #         'response': "It seems you provided an invalid rating. Please rate our service on a scale of 1 to 5."
        #     }

    def handle_exit(self) -> Dict[str, Any]:
        # Handle user saying goodbye or exit
        return {
            'response': "Goodbye! Thank you for reaching out. If you need assistance in the future, feel free to contact us again. Have a great day!"
        }

# Main interaction 
if __name__ == "__main__":
    agent = TechnicalSupportAgent()
    user_id = "user123"
    user_details = {"user_id": user_id}

    print("Bot: Hi, I am your technical assistant. How may I assist you?")
    while True:
        user_message = input("You: ").lower()
        
        # Check for exit phrases like "thank you" or "goodbye"
        if any(phrase in user_message for phrase in ["thank you", "goodbye", "thanks", "exit", "bye"]):
            # Ask for feedback when user says "thank you", "goodbye", or similar
            print("Bot: Thank you for using our service! Please rate your experience on a scale of 1 to 5.")
            feedback = input("You: ").strip()  # Adding strip to clean up any whitespace issues
            if feedback in ['1', '2', '3', '4', '5']:
                print(f"Bot: Thank you for your feedback! You rated us: {feedback}.")
            else:
                print("Bot: It seems you provided an invalid rating. Please rate our service on a scale of 1 to 5.")
            break  # Exit the conversation
        else:
            response = agent.get_support_response(user_details, user_message, user_id)
            print("Bot: ", response.get('response', 'For this service pls visit(https://www.airtel.in/airtel-thanks-app).'))
