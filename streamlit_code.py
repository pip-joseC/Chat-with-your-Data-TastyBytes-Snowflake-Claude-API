import numpy as np
import pandas as pd
import streamlit as st
from snowflake.snowpark import Session
import altair as alt
import os
from dotenv import load_dotenv
import time
from PIL import Image
from pathlib import Path

from snowflake.snowpark import Session
import anthropic

# Importing my own made functions
from app_backend.backend import *

# TODO:
# - Checar TODOs marcados en el código del chat
# - Implement a button or switch that can activate 2 different modes:
#       - **Precission mode**: This mode guarantees the best output, at the cost of more tokens used by Claude API. It will use the system prompt ``'claude_prompt_fully_improved.md'``.
#       - **Token-saving mode**: Thid mode sacrifices some accuracy on the final output, but consumes much Claude API less tokens. It will use the system prompt ``'claude_prompt_original.md' 
# - Checar video de Youtube para hacer fondo con degradado, elegir colores azulados y naranjas (colores de Snowflake y Claude), y cambiar el color theme de la app (para que los botones de las tabs en el dashboard no se vean rojos, por ejemplo)
# - Pedirle a Claude que revise la carpeta donde está el repositorio y que organice los archivos, además de que modifique las partes del código necesarias para la lectura de los archivos ya en sus carpetas correspondientes
# - Implementar un cuadro de diálogo que pida las credenciales de Claude y Snowflake si le voy a hacer deploy a la app y si puedo pedirle directamente pedir las credenciales (solo si es fácil pues xd)
#       - Antes de hacer lo anterior, preguntarle a Claude si es buena práctica hacer esto o si tengo que encriptar las credenciales que me den para evitar pedos de seguridad
# - COn la final version lista, pedirle a Claude que genere múltiples casos de prueba para cada tipo de gráfica o de pregunta (específica o vaga) (preguntas y qué gráficas esperaría), mpinimo 10 ejemplos en total
#       - Luego, probar las preguntas y las que jalen chido, grabar pantalla de solo la app y guardar los demos en GIFs (verificar si es buena idea con Claude)  
# Pedirle a Claude que lea el repo y que genere un README detallado con los archivos que hay, que incluya el setup necesario para ejecutar la app (recuerda que cargar la base de datos de Tasty bytes a Snowflake con el primer Notebook es necesario)

###### SNOWFLAKE AND CLAUDE CONNECTION

# Change folder to current directory of the Jupyter Notebook
current_path=os.path.dirname(__file__)
os.chdir(current_path)

# Load environment variables from .env file
load_dotenv(override=True) # override=True para que no haya conflictos con la Claude API Key en el .env 

if 'claude_client' not in st.session_state: # Connecting to Claude API and saving the connection. This will only execute once
    # Connecting to Claude API
    client = anthropic.Anthropic()
    st.session_state.claude_client = client # Saving the connection on the session state

if 'snow_session' not in st.session_state: # Connecting to Snwoflake and saving the connection. This will only execute once
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
    st.session_state.snow_session = session # Saving the connection on the session state


# APP displayed text
st.markdown('# :truck: Tasty Bytes Chatbot :hamburger:', text_alignment='center')
st.markdown('## *Claude API integrated with Snowflake on Tasty Bytes database*', text_alignment='center')
st.divider()
st.markdown("Write a question in natural language about Tasty Bytes current performance *(database date range: 2019-01-01 - 2022-11-01)*.")
# st.text("\n")
st.markdown('Be specific for better results, but if you are not sure what to ask, you can ask a generic question and Claude will guide you.')
st.divider()
# st.text_input()


if 'messages' not in st.session_state: # Initialize chat history
    st.session_state.messages = []
if 'claude_messages' not in st.session_state: # Initialize chat history for the Claude API
    st.session_state.claude_messages = []
if 'generation_status' not in st.session_state: # Initialize generation status variable
    st.session_state.generation_status = 'initialized'
if 'tokens' not in st.session_state: # Initialize tokens used array
    st.session_state.tokens = np.zeros(4)
if 'user_question' not in st.session_state:
    st.session_state.user_question = ''
if 'aclarations' not in st.session_state:
    st.session_state.aclarations = {}
# if 'ai_answer' not in st.session_state: # Initialize ai_answer variable where the generated SQL query may be found
#     st.session_state.ai_answer = {}

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message['role']):
        st.markdown(message['content'])

image = Image.open('Claude full icon orange.png').resize((30, 30)) #Loading Claude Icon image and resizing

# Loading system prompt
sys_prompt = Path('claude_prompt_fully_improved.md').read_text(encoding='utf-8')

################################################################################
# JUST FOR TESTING: CREATING TEST VARIABLES TO CHECK HOW THE APP LOOKS AND WORKS

st.session_state.generation_status = 'ready' # Skipping Claude generation
# TODO: Also skip the snowflake step
st.session_state.user_question = 'Is the loyalty program working?' 
st.session_state.aclarations = {'clarif_question': 'What does "working" mean to you? How would you like to judge the loyalty program? By country or by client and by which metric?', 
                                'user_clarif': 'I would like to judge the loyalty program using the average total sales and average number of locations visited per loyalty member, by country.'}
st.session_state.ai_answer = {'explanation': "This query returns one row per country, showing the number of loyalty members who have placed at least one order (the view only includes customers with orders), the average lifetime sales per member (`total_sales`, the sum of `order_total` per customer), and the average number of distinct locations each member has visited. Countries are ranked from highest to lowest average sales per member. Note that `country` is the customer's residence, not where purchases happened."}
generated_query = 'SELECT\n    c.country,\n    COUNT(DISTINCT c.customer_id) AS number_members,\n    AVG(c.total_sales) AS avg_total_sales,\n    AVG(ARRAY_SIZE(c.visited_location_ids_array)) AS avg_visited_locations\nFROM tasty_bytes.analytics.customer_loyalty_metrics_v AS c\nGROUP BY 1\nORDER BY 3 DESC;'
query_result = pd.read_csv('test_df.csv')

#################################################################################

if st.session_state.generation_status != 'ready': # Checking if the genearted query is not ready yet 
    # Reacting to the user 
    if user_input := st.chat_input("Ask anything about Tasty Bytes"): # used the := operator to assign the user's input to the prompt variable and checked if it's not None in the same line
        # This will execute after the user has enter their prompt

        # Showing the user question in the chat and saving it on the streamlit message history 
        st_chat_msg(role='user', txt=user_input)
        if st.session_state.generation_status == 'initialized':
            ### SQL QUERY GENERATION ###
            with st.spinner("Trying to generate the query..."): # Adding a loading spinner for this process
                ai_answer, used_tokens, msg_hist = generate_sql(user_question=user_input, system=sys_prompt, client=client)
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
                                                                                     client=client)
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
                query_result = session.sql(ai_answer['query']).to_pandas()
        except Exception as e:
            st.warning('An error occured, please wait until Claude fixes it.', icon="⚠️")
            time.sleep(1)
            if attempt == 3: # If maximum attempts reached, raise an error and stop the streamlit program
                st.write('Maximimum number of attempts reached, Claude could not fix the SQL query') # TODO
                break
            # If an error occurs and there are still enough attempts, the fix_bug() function will execute
            error_message = str(e) # Retrieving the error explicitly for Claude
            with st.spinner("Claude is fixing the problem..."):
                ai_answer, used_tokens_now, msg_hist = fix_bug(ai_query_bugged=ai_answer['query'], 
                                                               error_msg=error_message, 
                                                               system_prompt=sys_prompt, 
                                                               messages=st.session_state.claude_messages, 
                                                               client=client)
                st.session_state.tokens += used_tokens_now # Adding up the used tokens
        else: 
            # If no errors where found, there is no need to fix the query and we can break the for loop
            st.session_state.ai_answer = ai_answer # Saving the ai answer on the session state, in case an error was fixed
            st.success('Done!')
            break

    n = len(query_result)
    final_df = query_result.round(2).head(100) # Rounding the columns of the dataframe that are Decimal type and Limiting the maximum number of rows to the first 200 for saving Claude tokens
    is_truncated = True if len(final_df) < n else False # Checking wether the table was truncated or not (If rows were removed after showing the first 200 rows)
    csv_result = final_df.to_csv(index=False) # Converting it into CSV text

    st.session_state.dataframe = final_df # Saving the dataframe on a session state variable
    # st.session_state.generated_query = ai_answer['query'] # Saving the generated query on a session state variable

    sys_prompt_dash = Path('dashboard_prompt.md').read_text(encoding='utf-8')

    with st.spinner("Finally, claude is generating the final dashboard with the results..."):
        ai_answer_dash, used_tokens_now = generate_dashboard(user_question=st.session_state.user_question, # TODO: NEEDS TO BE TESTED IF IT WORKS PROPERLY
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

    time.sleep(2) # ADDING A 2 SECONDS COOLDOWN JUST FOR TESTING
    st.switch_page("pages/dashboard.py") # Changing page automatically here 

############ SCRIPT TO RUN STREAMLIT ON CONDA ENVIRONMENT
# & C:\Users\sorak\miniconda3\envs\ClaudeSnowflake\python.exe -m streamlit run "c:/Users/sorak/Documents/##REPOSITORIOS/Chat-with-your-Data-TastyBytes-Snowflake-Claude-API/streamlit_code.py"