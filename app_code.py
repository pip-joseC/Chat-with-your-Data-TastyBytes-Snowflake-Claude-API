import os
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from snowflake.snowpark import Session
# from snowflake.snowpark.functions import col, sum as sum_, avg, count

# import sqlglot
# from sqlglot.errors import ParseError, TokenError

import json
from pathlib import Path

import anthropic

# TODO: COPIAR Y PEGAR EL CÓDIGO DEL JUPYTER NOTEBOOK CON LOS ERRORES CORREGIDOS

#################################### FUNCTION DEFINITION ####################################

def add_user_msg(msgs, txt):
    ##### Adds an user message to the history #####
    user_msg = {'role': 'user', 'content':txt}
    msgs.append(user_msg)

def add_assistant_msg(msgs, txt):
    ##### Adds an assistant (AI) message to the history #####
    assistant_msg = {'role': 'assistant', 'content':txt}
    msgs.append(assistant_msg)

def chat(msgs, model, max_tokens=1000, system_prompt=None, output_format=None):
    # Creates a chat with the corresponding message history
    params = {
        'model': model,
        'max_tokens': max_tokens,
        'messages': msgs
    }
    if system_prompt:
        params['system'] = system_prompt
    if output_format:
        params['output_config'] = {'format': output_format}

    output = client.messages.create(**params)
    # Joining all text blocks, and checking if the block is a TextBlock
    return "".join(b.text for b in output.content if b.type == "text")

def chat_and_tokens(msgs, model, max_tokens=1000, use_cache=True, system_prompt=None, output_format=None):
     ##### Creates a chat with the corresponding message history, and outputs the input and output tokens used #####
    params = {
        'model': model,
        'max_tokens': max_tokens,
        'messages': msgs
    }
    if system_prompt:
        if use_cache: # This will execute if cache usage is needed
            params['system'] = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}  # Configuring the system prompt to be written in the cache. Lasts 5 minutes by default
                }
            ]
        else: # This will execute if cache usage is not needed
            params['system'] = system_prompt
    if output_format:
        params['output_config'] = {'format': output_format}

    output = client.messages.create(**params)
    # Using an array for saving the tokens used, so for future usages, we can add up the tokens used
    tokens_used = np.array([output.usage.input_tokens, output.usage.output_tokens, output.usage.cache_creation_input_tokens, output.usage.cache_read_input_tokens])
    # Joining all text blocks, and checking if the block is a TextBlock
    return "".join(b.text for b in output.content if b.type == "text"), tokens_used


def generate_sql(user_question, system):
    """
    Takes a user question and a system prompt and generates a SQL query using the Claude API.

    Parameters
    ----------
    user_question : str
        Question input by the user.
    system : str
        System prompt for Claude, with all the specifications and database documentation.

    Returns
    ----------
    ai_answer : dict
        Claude's answer as a dict, loaded from a JSON structure.
    tokens : list[int]
        A list of input, output and cache tokens used on the Claude API call. 
        Its structure is ``[input_tok, output_tok, cache_creation_tok, cache_read_tok]``.
    messages : list[dict]
        Message history of user-assistant conversation.
    """
    # Creating a JSON Schema that Claude will use for the output
    sql_schema = {
        "type": "json_schema",
        "schema": {
            "anyOf": [
                { # Output Schema in case the user question is simple or doesnt need a clarification
                    "type": "object",
                    "properties": {
                        "question_type": {"type": "string", "const": "sql"},
                        "query": {
                            "type": "string",
                            "description": "Executable SQL Query that answers the question.",
                        },
                        "explanation": {
                            "type": "string",
                            "description": "Brief explanation of the query of no more than 3 sentences.",
                        },
                    },
                    "required": ["question_type", "query", "explanation"],
                    "additionalProperties": False,
                },
                { # Output schema in case the user question needs a clarification
                    "type": "object",
                    "properties": {
                        "question_type": {"type": "string", "const": "clarify"},
                        "message": {
                            "type": "string",
                            "description": "Brief clarification question for the user.",
                        },
                    },
                    "required": ["question_type", "message"],
                    "additionalProperties": False,
                },
            ]
        },
    }

    prompt = f"Write an SQL query in order to answer the user's question about Tasty Bytes: {user_question}" # User question un natural language
    # Later, this variable will recieve the input of the streamlit app, like:
    # user_question = input('Ask a question about Tasty Bytes.') 

    messages = []
    add_user_msg(messages, prompt) # Adding the user question prompt to the message history

    ai_answer, tokens = chat_and_tokens( # Calling Claude API to write the SQL query
        messages,
        model='claude-sonnet-5-5',
        max_tokens=2000,
        system_prompt=system,
        output_format=sql_schema,
    )
    add_assistant_msg(messages, ai_answer) # Adding the user question prompt to the message history
    ai_answer = json.loads(ai_answer) # Converting the string generated by Claude into an JSON (dict)

    return ai_answer, tokens, messages # The message history will be needed for multi-turn conversations in case an aclaration is needed

def generate_sql_after_aclaration(messages, system, clarif):
    """
    Takes the aclaration question made by Claude, the response of the user and the same system prompt for generating a SQL query using the Claude API,
    after Claude identified that the users question is too vague.

    Parameters
    ----------
    messages : list[dict]
        Message history of user-assistant conversation.
    system : str
        System prompt for Claude, with all the specifications and database documentation.
    clarif : str
        Clarification made by the user after Claude's question

    Returns
    ----------
    ai_answer : str
        Claude's answer as a string, but with a JSON structure.
    tokens : list[int]
        A list of input, output and cache tokens used on the Claude API call. 
        Its structure is ``[input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens]``.
    """
    
    # Creating a JSON Schema that Claude will use for the output
    sql_schema = {
        "type": "json_schema",
        "schema": {
            "anyOf": [
                { # Output Schema in case the user question is simple or doesnt need a clarification
                    "type": "object",
                    "properties": {
                        "question_type": {"type": "string", "const": "sql"},
                        "query": {
                            "type": "string",
                            "description": "Executable SQL Query that answers the question.",
                        },
                        "explanation": {
                            "type": "string",
                            "description": "Brief explanation of the query of no more than 3 sentences.",
                        },
                    },
                    "required": ["question_type", "query", "explanation"],
                    "additionalProperties": False,
                },
                { # Output schema in case the user question needs a clarification
                    "type": "object",
                    "properties": {
                        "question_type": {"type": "string", "const": "clarify"},
                        "message": {
                            "type": "string",
                            "description": "Brief clarification question for the user.",
                        },
                    },
                    "required": ["question_type", "message"],
                    "additionalProperties": False,
                },
            ]
        },
    }

    add_user_msg(messages, f'User Clarification: {clarif}') # Adding the user clarification to the conversation

    prompt = f"Write an SQL query in order to answer the original user's question about Tasty Bytes, taking into account the recent user clarification." 
    add_user_msg(messages, prompt) # Adding the aclaration prompt to the message history

    ai_answer, tokens = chat_and_tokens( # Calling Claude API to write the SQL query
        messages,
        model='claude-sonnet-5-5',
        max_tokens=2000,
        system_prompt=system,
        output_format=sql_schema,
    )
    ai_answer = json.loads(ai_answer) # Converting the string generated by Claude into an JSON (dict)

    return ai_answer, tokens

#################################### WORKING CODE ####################################

# Change folder to current directory of the Jupyter Notebook
current_path=os.getcwd()
os.chdir(current_path)

# Load environment variables from .env file
load_dotenv(override=True) # override=True para que no haya conflictos con la Claude API Key en el .env 

# Connecting to Claude API
client = anthropic.Anthropic()

# Connection parameters for establishing a Snowpark session (Snowflake)
# These environment variables must be set with real credentials before running
connection_params = {
    "account": os.getenv("SNOWFLAKE_ACCOUNT"),
    "user": os.getenv("SNOWFLAKE_USER"),
    "password": os.getenv("SNOWFLAKE_PASSWORD"),
    "role": os.getenv("SNOWFLAKE_ROLE"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
    "database": os.getenv("SNOWFLAKE_DATABASE"),
    "schema": os.getenv("SNOWFLAKE_SCHEMA"),
}

# Create a Snowpark session using the connection parameters
session = Session.builder.configs(connection_params).create()

# Loading system prompt
sys_prompt = Path('claude_prompt_fully_improved.md').read_text(encoding='utf-8')
# Asking the user for a question about Tasty Bytes
question = input('Ask a question in order to get insights about Tasty Bytes:') # TODO: change this input later when the streamlit app is developed.

ai_answer, used_tokens, msg_hist = generate_sql(user_question=question, system=sys_prompt)

if ai_answer['question_type'] == 'clarify': # This will execute only if Claude needs an aclaration from the user
    clarification = input(ai_answer['message']) # TODO: change this input later when the streamlit app is developed.
    ai_answer, used_tokens_now = generate_sql_after_aclaration(messages=msg_hist, system=sys_prompt, clarif=clarification)
    used_tokens += used_tokens_now