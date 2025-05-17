import json
import random
import re
from typing import Optional, List, Dict, Any

import streamlit as st
from pydantic import BaseModel, ValidationError
from ollama import chat

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
MODEL_NAME = "llama3.1:8b"  # update for your local Ollama model tag

# -----------------------------------------------------------------------------
# Response models (strict schema enforcement via Pydantic)
# -----------------------------------------------------------------------------
class IdentityAnswer(BaseModel):
    response: str
    is_question: bool
    is_correct_guess: bool

# -----------------------------------------------------------------------------
# Identity generation functions
# -----------------------------------------------------------------------------
def generate_identity(identity_type: str, custom_details: str = ""):
    """Generate a character identity based on user preferences"""
    
    # Create prompt based on the identity type
    if identity_type == "Random Character":
        prompt = """Generate a random identity for a guessing game. Include historical figures, fictional characters, 
celebrities, professionals, etc. The player will try to guess who this is through yes/no questions."""
    elif identity_type == "Historical Figure":
        prompt = """Generate a historical figure identity for a guessing game. Choose someone significant from 
any time period in history. The player will try to guess who this is through yes/no questions."""
    elif identity_type == "Fictional Character":
        prompt = """Generate a fictional character identity for a guessing game. This could be from literature, 
movies, TV shows, comics, etc. The player will try to guess who this is through yes/no questions."""
    elif identity_type == "Profession/Role":
        prompt = """Generate an identity based on a profession or role for a guessing game. 
This could be any occupation (doctor, astronaut, teacher, etc.) or role (parent, leader, student, etc.) 
The player will try to guess what this profession/role is through yes/no questions."""
    elif identity_type == "Custom":
        prompt = f"""Generate an identity for a guessing game based on these details: {custom_details}
The player will try to guess who/what this is through yes/no questions."""
    else:
        return None
    
    system_prompt = """
You are an identity generator for a yes/no guessing game. Create a compelling identity that players can guess through yes/no questions.

Your task is to:
- Create a specific identity (person, character, profession, or concept)

**Your output must be just the name of the identity, no other text.**
    """

    max_retries = 3
    temperature = 0.7
    
    for _ in range(max_retries):
        raw = chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            format=None,
            options={"temperature": temperature},
        ).message.content.strip()
    
    return raw

# -----------------------------------------------------------------------------
# Prompt template
# -----------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are identity: {identity}.

You are playing a guessing game with the user. They are trying to figure out who or what you are.

Rules for you (the AI):
- For questions that gives clues about your identity, only respond with "yes" or "no".
- If the question is ambiguous or unanswerable, ask the user to clarify to help you answer.
- If the user asks if you are {identity}, congratulate them, set "is_correct_guess": true and end the game.
- Keep answers short.
- If the user does not give a direct guess or asks a question that is not a yes/no question, encourage the user to ask a yes/no question and set "is_question": false.
- Drive the conversation towards the game, do not talk about anything else.

# Output format:
Respond **EXCLUSIVELY** with a single JSON object and *nothing* else. The JSON must match exactly:
{{
  "response": "string",           # Your reply to the user
  "is_question": true|false,      # True if the question is a part of the game (yes/no or identity guess). Else false.
  "is_correct_guess": true|false  # True if the user correctly guessed your identity. Else false.
}}

NO markdown fences, headings, pre-ambles, or extra text before/after the JSON.
"""

# -----------------------------------------------------------------------------
# LLM helper with robust JSON extraction
# -----------------------------------------------------------------------------
JSON_RE = re.compile(r"\{.*?\}", re.S)

def ask_identity_ai(
    user_input: str,
    identity: str,
    max_retries: int = 3,
    temperature: float = 0.2,
) -> Optional[IdentityAnswer]:
    """Send user input to the local LLM and return a validated IdentityAnswer."""
    system_prompt = SYSTEM_PROMPT.format(identity=identity)

    for _ in range(max_retries):
        raw = chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            format="json",
            options={"temperature": temperature},
        ).message.content.strip()

        # Fast path
        try:
            return IdentityAnswer(**json.loads(raw))
        except (json.JSONDecodeError, ValidationError):
            pass

        # Fallback – extract first {...}
        m = JSON_RE.search(raw)
        if m:
            try:
                return IdentityAnswer(**json.loads(m.group(0)))
            except (json.JSONDecodeError, ValidationError):
                pass
    return None

# -----------------------------------------------------------------------------
# Session‑state helpers
# -----------------------------------------------------------------------------
def reset_game() -> None:
    """Reset the game state with a new identity"""
    # Always use a generated identity
    identity_type = st.session_state.get("identity_type", "Random Character")
    custom_details = st.session_state.get("custom_details", "")
    new_identity = generate_identity(identity_type, custom_details)
    if new_identity:
        st.session_state.identity = new_identity
    else:
        # Fallback in case generation fails
        st.session_state.identity = "Albert Einstein"
    
    st.session_state.question_count = 0
    st.session_state.game_over = False
    st.session_state.setup_complete = True
    st.session_state.messages = [
        (
            "System",
            "Guess the secret identity using yes/no questions.  "
            "\nTry to guess in as few questions as possible!",
        )
    ]

def setup_game(identity_type: str, custom_details: str = "") -> bool:
    """Set up a new game with the selected identity type"""
    # Generate a character based on user preference    
    #st.session_state.identity = ""
    # Store the identity type and custom details for later regeneration
    st.session_state.identity_type = identity_type
    st.session_state.custom_details = custom_details

def init_state() -> None:
    """Initialize the session state"""
    if "setup_complete" not in st.session_state:
        st.session_state.setup_complete = False
        
    if "messages" not in st.session_state and st.session_state.get("setup_complete", False):
        reset_game()

# -----------------------------------------------------------------------------
# Main app
# -----------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Guess Who I Am - AI game", page_icon="🕹️")
    init_state()

    st.title("Guess Who I Am")
    
    # Game setup screen
    if not st.session_state.get("setup_complete", False):
        st.header("Game Setup")
        
        identity_types = [
            "Random Character",
            "Historical Figure",
            "Fictional Character", 
            "Profession/Role",
            "Custom"
        ]
        
        identity_type = st.selectbox(
            "Choose what type of identity you want to guess:",
            identity_types
        )        
        custom_details = ""
        if identity_type == "Custom":
            custom_details = st.text_area(
                "Describe the type of identity you want (e.g., 'a famous scientist from the 20th century' or 'a superhero from Marvel comics'):",
                height=100
            )
        
        start_col1, start_col2 = st.columns([1, 1])
        with start_col1:
            if st.button("Start Game"):
                with st.spinner("Setting up your game..."):
                    setup_game(identity_type, custom_details)
                    reset_game()
                    st.rerun()
        # Preview section that explains the different identity types
        with st.expander("About the Identity Types"):
            st.markdown("""
            - **Random Character**: Generate a completely random identity that could be anyone or anything.
            - **Historical Figure**: A real person who lived in the past who made significant contributions or is well-known.
            - **Fictional Character**: A character from books, movies, TV shows, comics, or other fictional sources.
            - **Profession/Role**: A specific job, occupation, or social role.
            - **Custom**: Specify your own parameters for what kind of identity you want to guess.
            """)
        
        st.stop()

    # Sidebar with question counter and give up button
    st.sidebar.title("Game Progress")
    st.sidebar.metric("Questions asked", st.session_state.question_count)
    
    # Give up button in sidebar - available at all times
    if st.sidebar.button("🏳️ Give Up"):
        give_up_message = f"You gave up. The identity was **{st.session_state.identity}**."
        st.session_state.messages.append(("System", give_up_message))
        st.session_state.game_over = True
        st.rerun()

    # Chat history
    use_chat = hasattr(st, "chat_message")
    for sender, msg in st.session_state.messages:
        if use_chat:
            role = "assistant" if sender in {"AI", "System"} else "user"
            st.chat_message(role).markdown(msg)
        else:
            st.markdown(f"**{sender}:** {msg}")

    # End‑game screen --------------------------------------------------------
    if st.session_state.game_over:
        if st.session_state.question_count > 0:
            st.sidebar.success(f"Game finished in {st.session_state.question_count} questions!")
        else:
            st.sidebar.info("Game finished!")
            
        col1, col2 = st.columns([1, 1])
        
        with col1:
            if st.button("🔄 Restart with Same Settings"):
                # Keep the same identity type settings but get a new identity
                reset_game()
                st.rerun()
                
        with col2:
            if st.button("⚙️ New Game Setup"):
                # Go back to the setup screen
                st.session_state.setup_complete = False
                st.rerun()

    # ----------------------------------------------------------------------
    # User input
    prompt = (
        st.chat_input("Ask a yes/no question or make a guess…")
        if hasattr(st, "chat_input")
        else st.text_input("Type here…")
    )
    if not prompt:
        st.stop()

    # Echo user message
    if use_chat:
        st.chat_message("user").markdown(prompt)
    else:
        st.markdown(f"**You:** {prompt}")
    st.session_state.messages.append(("You", prompt))

    # Call LLM
    with st.spinner("AI thinking…"):
        answer = ask_identity_ai(
            prompt, 
            st.session_state.identity,
        )
        
        # Hardcode is_question to true for yes/no questions
        if answer and answer.response.lower() in ["yes", "no"]:
            answer.is_question = True

        # Hardcode is_correct_guess to true if the user guessed the identity
        if answer and st.session_state.identity.lower() in prompt.lower():
            answer.response = "Yes!"
            answer.is_correct_guess = True
            answer.is_question = False

    if answer is None:
        err = "⚠️ AI returned invalid JSON. Try again."
        if use_chat:
            st.chat_message("assistant").markdown(err)
        else:
            st.markdown(f"**System:** {err}")
        st.session_state.messages.append(("System", err))
        st.stop()

    # Display AI reply
    if use_chat:
        st.chat_message("assistant").markdown(answer.response)
    else:
        st.markdown(f"**AI:** {answer.response}")
    st.session_state.messages.append(("AI", answer.response))

    # End‑game logic ---------------------------------------------------------
    if answer.is_correct_guess:
        st.session_state.question_count += 1
        end_message = f"🎉 Correct! The identity was **{st.session_state.identity}**. You solved it in **{st.session_state.question_count}** questions! 🎉"
        st.session_state.messages.append(("System", end_message))
        # Display end message
        if use_chat:
            st.chat_message("assistant").markdown(end_message)
        else:
            st.markdown(f"**System:** {end_message}")
        st.session_state.game_over = True
        
    # Refresh page if game is over to show end game UI
    if st.session_state.game_over:
        st.rerun()
    
    # Update question count if it's a valid question
    if answer.is_question:
        st.session_state.question_count += 1
        # Store the answer to display after rerun
        st.session_state.last_answer = answer
        # Force rerun to update the counter in UI immediately
        st.rerun()

if __name__ == "__main__":
    main()