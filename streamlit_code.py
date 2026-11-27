import numpy as np
import streamlit as st
from snowflake.snowpark import Session
import os
import base64, io
from dotenv import load_dotenv
import time
from PIL import Image
from pathlib import Path
from snowflake.snowpark import Session
import anthropic

# Importing my own made functions
from app_backend.prompting import *
from app_backend.streamlit import *

# Loading the background written in CSS and the color icon for the chat messages
st.markdown(
    """
    <style>
    [data-testid="stAppScrollToBottomContainer"] {
    background: linear-gradient(to bottom, #004e92, #000428);
    }

    [data-testid="stChatMessageAvatarUser"] {
        background-color: #00bfff;
    }
    </style>
    """, 
    unsafe_allow_html=True)

# Hiding the sidebar by default
st.set_page_config(initial_sidebar_state="collapsed")
# Disabling the buttion for showing and collapsing the sidebar
st.markdown(
    """
    <style>
        [data-testid="stSidebar"] {
            display: none;
        }
        [data-testid="collapsedControl"] {
            display: none;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

###### SNOWFLAKE AND CLAUDE CONNECTION
# Change folder to current directory
current_path=os.path.dirname(__file__)
os.chdir(current_path)

# Asking for he credentials (previously done with env variables, but now we need to adapt for any user having their own credentials)
if "creds" not in st.session_state:
    ask_credentials() # Asking the user their credentials on a dialog window
    # st.info("Complete all fields to proceed.")
    st.stop()

if 'claude_client' not in st.session_state: # Connecting to Claude API and saving the connection. This will only execute once
    # Connecting to Claude API
    client = anthropic.Anthropic(api_key=st.session_state.creds['api_key'])
    st.session_state.claude_client = client # Saving the connection on the session state

if 'snow_session' not in st.session_state: # Connecting to Snwoflake and saving the connection. This will only execute once
    # Connection parameters for establishing a Snowpark session (Snowflake)
    connection_params = {
        "account": st.session_state.creds['account'],
        "user": st.session_state.creds['user'],
        "password": st.session_state.creds['password'],
        "role": "TASTY_READ_ONLY", # Creaating the connection with the "read only" role that was created
        "warehouse": "TASTY_DE_WH", # Assigning to the small warehouse that was created previously just for analytics
        "database": "TASTY_BYTES",
    }

    # Create a Snowpark session using the connection parameters
    session = Session.builder.configs(connection_params).create()
    st.session_state.snow_session = session # Saving the connection on the session state

if 'messages' not in st.session_state: # Initialize chat history
    st.session_state.messages = []
if 'generation_status' not in st.session_state: # Initialize generation status variable
    st.session_state.generation_status = 'initialized'
if 'aclarations' not in st.session_state:
    st.session_state.aclarations = {}
if 'claude_mode' not in st.session_state:
    st.session_state.claude_mode = ':rainbow[Precission Mode]'
if 'mode_disabled' not in st.session_state:
    st.session_state.mode_disabled = False

# APP displayed text
st.markdown('# :truck: Tasty Bytes Chatbot :hamburger:', text_alignment='center')
st.markdown('## *Claude API integrated with Snowflake on Tasty Bytes database*', text_alignment='center')
st.divider()
st.markdown("Write a question in natural language about Tasty Bytes current performance *(database date range: 2019-01-01 - 2022-11-01)*.")
st.markdown('Be specific for better results, but if you are not sure what to ask, you can ask a generic question and Claude will guide you.')


st.radio( # Radio selection for choosing the claude mode (choosing the system prompt)
    "**Choose a Claude mode:**",
    [':rainbow[Precission Mode]', "*Token-saving Mode*"],
    captions=[
        "This mode guarantees the best output, at the cost of more tokens used by Claude API. (It will use the system prompt `'claude_prompt_fully_improved.md'`, which is very specific but very long too.)",
        "This mode sacrifices some accuracy on the final output, but consumes much Claude API less tokens. (It will use the system prompt `'claude_prompt_original.md'`, which is very short but not to clear.)"
    ],
    key='claude_mode',
    disabled=st.session_state.mode_disabled
)

st.divider()

@st.cache_resource
def load_avatar(path, size=128):
    img = Image.open(path).convert("RGBA").resize((size, size))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

image = load_avatar('assets/Claude full icon orange.png') #Loading Claude Icon image and resizing

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message['role'], avatar=image if message['role'] == 'assistant' else None):
        st.markdown(message['content'])

# Loading system prompt, depending on the selected mode
if st.session_state.claude_mode == ':rainbow[Precission Mode]':
    sys_prompt = Path('prompts/claude_prompt_fully_improved.md').read_text(encoding='utf-8')
else: 
    sys_prompt = Path('prompts/claude_prompt_original.md').read_text(encoding='utf-8')


if st.session_state.generation_status != 'ready': # Checking if the genearted query is not ready yet 
    # Reacting to the user 
    if user_input := st.chat_input("Ask anything about Tasty Bytes"): # used the := operator to assign the user's input to the prompt variable and checked if it's not None in the same line        
        # This will execute after the user has enter their prompt

        st.session_state.mode_disabled = True # Disabling the "Choose a Claude mode" radio button after receibing an user input
        # Showing the user question in the chat and saving it on the streamlit message history 
        st_chat_msg(role='user', txt=user_input)
        if st.session_state.generation_status == 'initialized':
            ### SQL QUERY GENERATION ###
            with st.spinner("Trying to generate the query..."): # Adding a loading spinner for this process
                ai_answer, used_tokens, msg_hist = generate_sql(user_question=user_input, system=sys_prompt, client=st.session_state.claude_client)
                st.session_state.user_question = user_input # Saving the user question on this session variable
                st.session_state.ai_answer = ai_answer # Saving the generated query and explanation on this session variable
                st.session_state.claude_messages = msg_hist # Saving the generated Claude chat history on this session variable
                st.session_state.tokens = used_tokens # Saving used tokens on this session variable

            # Checking wether Claude could generate the query itself or if it needs an extra clarification
            if ai_answer['question_type'] == 'sql': # This will execute only if Claude could generate the query right away
                ai_response = 'The query has generated successfully, it will be runned on Snowflake in a moment...'
                st_chat_msg(role='assistant', txt=ai_response, avatar=image) # Showing an "AI response" placeholder just to tell the user the SQL query has been generated
                st.session_state.generation_status = 'ready' # Updating generation_status on the session, in order to simbolize that the query is ready
                st.rerun() # Rerunning the script inmediatly, so that the program do not waits another user input
            elif ai_answer['question_type'] == 'clarify': # This will execute only if Claude needs an aclaration from the user
                ai_response = f"I need you to respond the following to get a proper query: {ai_answer['message']}" 
                st_chat_msg(role='assistant', txt=ai_response, avatar=image) # Showing AI message with the clarification question needed
                st.session_state.aclarations['clarif_question'] = ai_answer['message'] # Saving the AI question for clarification
                st.session_state.generation_status = 'needs clarif' # Updating generation_status on the session, in order to ask again the user input

        elif st.session_state.generation_status == 'needs clarif': 
            with st.spinner("Generating the query with the user's clarification..."): # Adding a loading spinner for this process
                ai_answer, used_tokens_now, msg_hist = generate_sql_after_aclaration(messages=st.session_state.claude_messages, 
                                                                                     system=sys_prompt, 
                                                                                     clarif=user_input, 
                                                                                     client=st.session_state.claude_client)
                st.session_state.aclarations['user_clarif'] = user_input # Saving the response of the user to the AI question for clarification
                st.session_state.ai_answer = ai_answer # Saving the generated query and explanation on this session variable
                st.session_state.claude_messages = msg_hist # Saving the generated Claude chat history on this session variable
                st.session_state.tokens += used_tokens_now # Adding up the used tokens

            st.session_state.generation_status = 'ready' 
            st.rerun() # Rerunning the script inmediatly, so that the program do not waits another user input

else: # If the genearted query is ready, the following will be executed
    # In this case, it will not wait for an user input and, instead, will run it directly on Snowflake

    ai_answer = st.session_state.ai_answer # Loading the ai answer from the session state
    ###### RUNNING SQL QUERY IN SNOWFLAKE AND SOLVING POSSIBLE ERRORS
    for attempt in [1,2,3]: # Maximum 2 more attempts (first execution + 2 extra attempts)
        try:
            with st.spinner("Running SQL query on Snowflake..."):
                query_result = st.session_state.snow_session.sql(ai_answer['query']).to_pandas() #Running the query on the snowflake session saved on the session state
        except Exception as e:
            st.warning('An error occured, please wait until Claude fixes it.', icon="⚠️")
            time.sleep(1)
            if attempt == 3: # If maximum attempts reached, raise an error and stop the streamlit program
                st.warning('Maximimum number of attempts reached, Claude could not fix the SQL query. Please try again and be more specific with your question.', icon="⚠️")
                attempt += 1 # attempt = 4 if the macimum attempts are reached and an error occurs at the end
                break
            # If an error occurs and there are still enough attempts, the fix_bug() function will execute
            error_message = str(e) # Retrieving the error explicitly for Claude
            with st.spinner("Claude is fixing the problem..."):
                ai_answer, used_tokens_now, msg_hist = fix_bug(ai_query_bugged=ai_answer['query'], 
                                                               error_msg=error_message, 
                                                               system_prompt=sys_prompt, 
                                                               messages=st.session_state.claude_messages, 
                                                               client=st.session_state.claude_client)
                st.session_state.tokens += used_tokens_now # Adding up the used tokens
        else: 
            # If no errors where found, there is no need to fix the query and we can break the for loop
            st.session_state.ai_answer = ai_answer # Saving the ai answer on the session state, in case an error was fixed
            st.success('Done!')
            break

    if attempt < 4: # Only executing the following if the attempt count is less than 4 
        n = len(query_result)
        final_df = query_result.round(2).head(100) # Rounding the columns of the dataframe that are Decimal type and Limiting the maximum number of rows to the first 200 for saving Claude tokens
        is_truncated = True if len(final_df) < n else False # Checking wether the table was truncated or not (If rows were removed after showing the first 200 rows)
        csv_result = final_df.to_csv(index=False) # Converting it into CSV text

        st.session_state.dataframe = final_df # Saving the dataframe on a session state variable
        st.session_state.generated_query = ai_answer['query'] # Saving the generated query on a session state variable 

        sys_prompt_dash = Path('prompts/dashboard_prompt.md').read_text(encoding='utf-8')

        with st.spinner("Finally, claude is generating the final dashboard with the results..."):
            ai_answer_dash, used_tokens_now = generate_dashboard(user_question=st.session_state.user_question, 
                                                                clarifs=st.session_state.aclarations, 
                                                                sql_explanation=st.session_state.ai_answer['explanation'], 
                                                                csv_text=csv_result, 
                                                                n_rows=n, 
                                                                truncated=is_truncated, 
                                                                system=sys_prompt_dash, 
                                                                client=st.session_state.claude_client) 
            st.session_state.tokens += used_tokens_now
        st.success('Done!')
        st.session_state.ai_dashboard = ai_answer_dash

        time.sleep(1)
        st.switch_page("pages/dashboard.py") # Changing page automatically here 

############ SCRIPT TO RUN STREAMLIT ON CONDA ENVIRONMENT
# & C:\Users\sorak\miniconda3\envs\ClaudeSnowflake\python.exe -m streamlit run "c:/Users/sorak/Documents/##REPOSITORIOS/Chat-with-your-Data-TastyBytes-Snowflake-Claude-API/streamlit_code.py"
