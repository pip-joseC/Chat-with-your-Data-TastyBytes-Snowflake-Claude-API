import numpy as np
import json

def add_user_msg(msgs, txt):
    """
    Appends an string, containing the **user** prompt, in a message history.

    Parameters
    ----------
    msgs : list[dict]
        Message history of user-assistant conversation (can be empty).
    txt : str
        User prompt.

    Returns
    ----------
    *None* (directly modifies the message history)
    """

    user_msg = {'role': 'user', 'content':txt}
    msgs.append(user_msg)

def add_assistant_msg(msgs, txt):
    """
    Appends an string, containing the **AI assistant** response, in a message history.

    Parameters
    ----------
    msgs : list[dict]
        Message history of user-assistant conversation (can be empty).
    txt : str
        AI response prompt.

    Returns
    ----------
    *None* (directly modifies the message history)
    """

    assistant_msg = {'role': 'assistant', 'content':txt}
    msgs.append(assistant_msg)

def chat_and_tokens(msgs, model, client, max_tokens=1000, use_cache=True, system_prompt=None, output_format=None):
    """
    Creates a chat with the corresponding message history

    Parameters
    ----------
    msgs : list[dict]
        Message history of user-assistant conversation (can be empty).
    model : str
        Name of Claude model.
    client : Anthropic object
        Connection to Claude API.
    max_tokens : int
        Maximum number of output tokens that can be used.
    use_cache : bool
        Activates (`True`) or deactiates (`False`) cache usage.
    system_prompt : str
        System prompt for Claude, containing details about how the AI should respond to the user.
    output_format : dict
        JSON schema that dictates the structure of the AI response.

    Returns
    ----------
    ai_answer : str
        Claude's answer wwith the code fixed as a string, but with a JSON structure.
    tokens_used : list[int]
        A list of input, output and cache tokens used on the Claude API call. 
        Its structure is ``[input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens]``.
    """

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
    ai_answer = "".join(b.text for b in output.content if b.type == "text")
    return ai_answer, tokens_used

def token_cost(in_tokens, out_tokens, cache_creation_tokens, cache_read_tokens):
    """
    Calculating token cost using the updated base cost of Sonnet 5.5 (from Nov 10th 2026 from https://platform.claude.com/docs/es/about-claude/pricing):
    input tokens: USD 2 / MTok, output tokens: USD 10 / MTok, cache creation input tokens (5 minutes): USD 2.5 / MTok, cache read input tokens: USD 0.1 / MTok

    Parameters
    ----------
    in_tokens : int
        The number of input tokens used.
    out_tokens : int
        The number of output tokens used.
    cache_creation_tokens : int
        The number of input tokens used to create the cache entry.
    cache_read_tokens : int
        The number of input tokens read from the cache.

    Returns
    ----------
    final_cost : float
        Cost in USD of the query.
    """

    if not cache_creation_tokens: # In case it is None when cache is not written
        cache_creation_tokens = 0
    if not cache_read_tokens: # In case it is None when cache is not read
        cache_read_tokens = 0

    
    in_cost = 2/1e6
    out_cost = in_cost*5
    cache_creat_cost = 2.5/1e6
    cache_read_cost = 0.2/1e6

    final_cost = in_tokens*in_cost + out_tokens*out_cost + cache_creation_tokens*cache_creat_cost + cache_read_tokens*cache_read_cost
    return final_cost

def generate_sql(user_question, system, client):
    """
    Takes a user question and a system prompt and generates a SQL query using the Claude API.

    Parameters
    ----------
    user_question : str
        Question input by the user.
    system : str
        System prompt for Claude, with all the specifications and database documentation.
    client : Anthropic object
        Connection to Claude API.

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
        client=client, 
        max_tokens=2000,
        system_prompt=system,
        output_format=sql_schema,
    )
    add_assistant_msg(messages, ai_answer) # Adding the user question prompt to the message history
    ai_answer = json.loads(ai_answer) # Converting the string generated by Claude into an JSON (dict)

    return ai_answer, tokens, messages # The message history will be needed for multi-turn conversations in case an aclaration is needed

def generate_sql_after_aclaration(messages, system, clarif, client):
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
    client : Anthropic object
        Connection to Claude API.

    Returns
    ----------
    ai_answer : dict
        Claude's answer with a JSON structure.
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
        client=client, 
        max_tokens=2000,
        system_prompt=system,
        output_format=sql_schema,
    )
    add_assistant_msg(messages, ai_answer) # Adding the user question prompt to the message history
    ai_answer = json.loads(ai_answer) # Converting the string generated by Claude into an JSON (dict)

    return ai_answer, tokens, messages

def fix_bug(ai_query_bugged, error_msg, system_prompt, messages, client):
    """
    Fixes the SQL code using a Claude API call.

    Parameters
    ----------
    ai_query_bugged : str
        The SQL query written by Claude that contains an error
    error_msg : str
        The error message raised by Snowpark
    system_prompt : str
        System prompt for Claude, with all the specifications and database documentation.
    messages : list[dict]
        Message history of user-assistant conversation.
    client : Anthropic object
        Connection to Claude API.

    Returns
    ----------
    ai_answer : dict
        Claude's answer wwith the code fixed with a JSON structure.
    tokens : list[int]
        A list of input, output and cache tokens used on the Claude API call. 
        Its structure is ``[input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens]``.
    messages : list[dict]
        Message history of user-assistant conversation.
    """ 

    prompt = f""" 
The SQL query below was generated earlier in this conversation and failed when executed in Snowflake.

<failed_query>
{ai_query_bugged}
</failed_query>

<snowflake_error>
{error_msg}
</snowflake_error>

Fix the cause of the error, but also review the query and fix other problems you might find. Keep the original intent, the schema rules and the SQL style. 
Reply with the usual JSON object, always with "question_type": "sql" (never "clarify"); in "explanation", state in one sentence what was wrong and what you changed.
    """

    # Creating a JSON Schema that Claude will use for the output
    sql_schema = { # Now, the only possible output schema could be the one where it outputs the SQL query
        "type": "json_schema",
        "schema": { 
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
    }

    add_user_msg(messages, prompt) # Adding the new prompt to the message history

    ai_answer, tokens = chat_and_tokens( # Calling Claude API to write the SQL query
        messages,
        model='claude-sonnet-5-5',
        client=client, 
        max_tokens=2000,
        system_prompt=system_prompt,
        output_format=sql_schema,
    )

    add_assistant_msg(messages, ai_answer) # Adding the user question prompt to the message history
    ai_answer = json.loads(ai_answer) # Converting the string generated by Claude into an JSON (dict)

    return ai_answer, tokens, messages

def generate_dashboard(user_question, clarifs, sql_explanation, csv_text, n_rows, truncated, system, client):
    """
    Generates the interpretation, key metrics and the chart properties for the final dashboard.

    Parameters
    ----------
    user_question : str
        Question input by the user.
    clarifs : dict
        Clarification made by the user after Claude's question, containing the clarification question and the user response.
    sql_explanation : str
        Claude's explanation of the generated SQL query.
    csv_text : str 
        Final table on CSV format.
    n_rows : int
        Number of rows of the original query output.
    truncated : bool
        Wether the final table was cut off or not (max. 100 are allowed).
    system : str
        System prompt for Claude, with all the specifications and database documentation.
    client : Anthropic object
        Connection to Claude API.

    Returns
    ----------
    ai_answer : dict
        Claude's answer as a dict, loaded from a JSON structure.
    tokens : list[int]
        A list of input, output and cache tokens used on the Claude API call. 
        Its structure is ``[input_tok, output_tok, cache_creation_tok, cache_read_tok]``.
    """
    # Creating a JSON Schema that Claude will use for the output
    dashboard_schema = {
    "type": "object",
    "properties": {
        "metrics": {"type": "array", "minItems": 1, 
            "items": {
            "type": "object",
            "properties": {
            "name": {"type": "string"},
            "value": {"type": "string"}
            },
            "required": ["name", "value"],
            "additionalProperties": False
        }
        },
        "chart": {
        "anyOf": [
            {
            "type": "object",
            "properties": {
                "mark": {
                "type": "string",
                "enum": ["bar", "line", "point", "rect"]
                },
                "title": {"type": "string"},
                "x": {"$ref": "#/$defs/channel"},
                "y": {"$ref": "#/$defs/channel"},
                "color": {
                "anyOf": [
                    {"$ref": "#/$defs/channel"},
                    {"type": "null"}
                ]
                },
                "tooltip": {
                "type": "array",
                "items": {"type": "string"}
                }
            },
            "required": ["mark", "title", "x", "y", "color", "tooltip"],
            "additionalProperties": False
            },
            {"type": "null"}
        ]
        },
        "interpretation": {"type": "string"}
    },
    "required": ["metrics", "chart", "interpretation"],
    "additionalProperties": False,
    "$defs": {
        "channel": {
        "type": "object",
        "properties": {
            "field": {"type": "string"},
            "type": {
            "type": "string",
            "enum": ["quantitative", "nominal", "ordinal", "temporal"]
            },
            "title": {"type": "string"},
            "sort": {
            "anyOf": [
                {
                "type": "string",
                "enum": ["-x", "-y"]
                },
                {"type": "null"}
            ]
            },
            "format": {"type": ["string", "null"]}
        },
        "required": ["field", "type", "title", "sort", "format"],
        "additionalProperties": False
        }
    }
    }

    clarify_question, clarify_answer = clarifs['clarif_question'], clarifs['user_clarif']

    prompt = f""" 
<results rows="{n_rows}" truncated="{truncated}">
{csv_text}
</results>

<sql_explanation>
{sql_explanation}
</sql_explanation>

<clarification>
<question>{clarify_question or "None"}</question>
<answer>{clarify_answer or "None"}</answer>
</clarification>

<user_question>
{user_question}
</user_question>
    """

    messages = []
    add_user_msg(messages, prompt) # Adding the user question prompt to the message history

    ai_answer, tokens = chat_and_tokens( # Calling Claude API to write the SQL query
        messages,
        model='claude-sonnet-5-5',
        client=client, 
        max_tokens=2000,
        system_prompt=system,
        output_format={"type": "json_schema", "schema": dashboard_schema},
        use_cache=False
    )

    # DES-COMENTAR DESPUÉS DEL TEST
    # ai_answer = json.loads(ai_answer) # Converting the string generated by Claude into an JSON (dict)

    return ai_answer, tokens # The message history will be needed for multi-turn conversations in case an aclaration is needed


#################################### WORKING CODE ####################################

# ###### SNOWFLAKE AND CLAUDE CONNECTION

# # Change folder to current directory of the Jupyter Notebook
# current_path=os.path.dirname(__file__)
# os.chdir(current_path)

# # Load environment variables from .env file
# load_dotenv(override=True) # override=True para que no haya conflictos con la Claude API Key en el .env 

# # Connecting to Claude API
# client = anthropic.Anthropic()

# # Connection parameters for establishing a Snowpark session (Snowflake)
# # These environment variables must be set with real credentials before running
# connection_params = {
#     "account": os.getenv("SNOWFLAKE_ACCOUNT"),
#     "user": os.getenv("SNOWFLAKE_USER"),
#     "password": os.getenv("SNOWFLAKE_PASSWORD"),
#     "role": os.getenv("SNOWFLAKE_ROLE"),
#     "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
#     "database": os.getenv("SNOWFLAKE_DATABASE"),
#     "schema": os.getenv("SNOWFLAKE_SCHEMA"),
# }

# # Create a Snowpark session using the connection parameters
# session = Session.builder.configs(connection_params).create()

# ###### SQL QUERY GENERATION

# # Loading system prompt
# sys_prompt = Path('prompts/claude_prompt_fully_improved.md').read_text(encoding='utf-8')
# # Asking the user for a question about Tasty Bytes
# question = input('Ask a question in order to get insights about Tasty Bytes:') # TODO: change this input later when the streamlit app is developed.

# ai_answer, used_tokens, msg_hist = generate_sql(user_question=question, system=sys_prompt)

# if ai_answer['question_type'] == 'clarify': # This will execute only if Claude needs an aclaration from the user
#     clarification = input(ai_answer['message']) # TODO: change this input later when the streamlit app is developed.
#     ai_answer, used_tokens_now, msg_hist = generate_sql_after_aclaration(messages=msg_hist, system=sys_prompt, clarif=clarification)
#     used_tokens += used_tokens_now

# ###### RUNNING SQL QUERY IN SNOWFLAKE AND SOLVING POSSIBLE ERRORS

# for attempt in [1,2,3]: # Maximum 2 more attempts (first execution + 2 extra attempts)
#     try:
#         query_result = session.sql(ai_answer['query']).to_pandas()
#     except Exception as e:
#         if attempt == 3: # If maximum attempts reached, raise an error and stop the streamlit program
#             print('Maximimum number of attempts reached, Claude could not fix the SQL query') # TODO
#             break
#         # If an error occurs and there are still enough attempts, the fix_bug() function will execute
#         error_message = str(e) # REtrieving the error explicitly for Claude
#         ai_answer, used_tokens_now, msg_hist = fix_bug(ai_query_bugged=ai_answer['query'], error_msg=error_message, system_prompt=sys_prompt, messages=msg_hist)
#         # used_tokens += used_tokens_now
#     else: 
#         # If no errors where found, there is no need to fix the query and we can break the for loop
#         break

# ###### GRAPHING THE RESULT USING CLAUDE TO COLLECT INSIGHTS
# final_df = query_result.round(2)
# csv_result = final_df.to_csv(index=False) # Rounding the columns of the dataframe that are Decimal type & Converting into CSV text