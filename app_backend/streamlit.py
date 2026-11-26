import pandas as pd
import streamlit as st
import time
import altair as alt

@st.dialog("Input your credentials", dismissible=False)
def ask_credentials():
    st.caption("These will only live on this current session, nothing will be saved or registered elsewhere.")
    # Asking the user their credentials with texts inputs
    account = st.text_input(":blue[Snowflake] Account ID")
    user = st.text_input(":blue[Snowflake] Username")
    password = st.text_input(":blue[Snowflake] Password", type="password")
    api_key = st.text_input(":orange[Anthropic] API key", type="password")
    
    if st.button("Connect", type="primary"): # Checking if the button was pressed
        if all([account, user, password, api_key]):
            # Saving everything on the session_state in a dictionary on 'creds'
            st.session_state.creds = dict(account=account, user=user, password=password, api_key=api_key)
            st.rerun() # Closes the dialog and reruns the app without it 
        else:
            st.error("ALL credentials are needed, complete all fields to proceed.") # This will pop up if the credentials are incomplete after the button is pressed

def stream_ai_response(ai_answer):
    # Function for writing ai responses as a stream of text
    for word in ai_answer.split():
        yield word + " "
        time.sleep(0.03)

def st_chat_msg(role, txt, avatar=None):
    # Displaying user or assistant sent string and adding it to the session state message history
    with st.chat_message(role, avatar=avatar):
        if role == 'user': 
            st.write(txt) # If role is user, it will just show the text 
        elif role == 'assistant':
            st.write_stream(stream_ai_response(txt)) # If role is assistant, it will show the text as a stream of words 
    st.session_state.messages.append({'role':role, 'content':txt})

def set_axis(cls, spec, mark):
    # Axis set up
    # ``cls`` should X or Y altair objects (cls = alt.X / alt.Y)
    # ``spec`` are the specifications of the given axis (chart_specs['x'] / chart_specs['y'])
    labelAngle = -45 if alt.X else alt.Undefined # If it is the X object, it will rotate -45 deegrees the x tick labels
    ax = cls(field=spec['field'], type=spec['type'], title=spec['title'],
               sort=spec['sort'] or alt.Undefined,
               axis=alt.Axis(format=spec['format'], labelAngle=labelAngle) if spec['format'] else alt.Axis(labelAngle=labelAngle)) 
    return ax.scale(zero=False) if mark in ('line','point') else ax # if the graph is a line or point chart, its scale won't start from zero, which is not the default

def set_color(spec, mark):
    # Color set up
    # The 'format' goes directly on the legend. 
    # On Heatmap (chart_specs['mark']='rect'), the color is the metric itself
    kw = {}
    if spec['format']: # Only in case chart_specs['color']['format'] is not None
        kw['legend'] = alt.Legend(format=spec['format'])
    if mark == 'rect': # Only in case the graph is a heatmap
        kw['scale'] = alt.Scale(scheme='blues')
    return alt.Color(field=spec['field'], type=spec['type'], title=spec['title'],
                     sort=spec['sort'] or alt.Undefined, **kw)

def build_graph(data, specs):
    # Returns an alt.Chart object, or none if no graph can be made (chart_specs['mark']=None)

    MARKS = {'bar': 'mark_bar', 'line': 'mark_line', 'point': 'mark_point', 'rect': 'mark_rect'} # marks dict with the corresponding mark name for alt.Chart
    if not specs or specs.get('mark') not in MARKS: # In case mark is None or an unexpected mark is made up
        return None

    channels = ["x", "y"] + (["color"] if specs["color"] else []) # Checking every channel (every key that contains a dict value on specs) and checking if 'color' is None or not
    fields = [specs[c]['field'] for c in channels] + list(specs.get('tooltip') or []) # Importing all the fields listed in every channel, just for the folowing verification
    if any(f not in data.columns for f in fields):  # If an column on specified on 'field' or 'tooltip' does not exist (hallucination from Claude), it will return None
        return None

    data = data.copy() # Copying the dataframe, so that the transformations only affect this new one

    # Transforming the fields that will be graphed if they are quatitative or temporal into the correct data type
    for c in channels:
        f, t = specs[c]['field'], specs[c]['type'] # Obtaining 2 lists, one with fields and the other with their corresponding type
        if t == 'quantitative':
            data[f] = pd.to_numeric(data[f])
        elif t == 'temporal':
            data[f] = pd.to_datetime(data[f])

    mark = specs['mark'] # Getting the type of graph ("mark type") that will be made

    # Obtaining the corresponging altair chart (alt.Chart(data).mark_bar() for 'bar' mark type, and so on...) and adding points just in case the graph is a line graph 
    chart = getattr(alt.Chart(data), MARKS[mark])(**({'point': True} if mark == 'line' else {}))
    chart = chart.encode(
        x=set_axis(alt.X, specs['x'], mark=mark), # Using set_axis() for X axis
        y=set_axis(alt.Y, specs['y'], mark=mark), # Using set_axis() for Y axis
        color=set_color(specs['color'], mark) if specs.get('color') else alt.Undefined, # Using set_color() for color if it exists, but if it is None, it uses alt.Undefined instead
        tooltip=specs.get('tooltip') or alt.Undefined, # Getting 'tooltip' and using it if it exists, but if it is None, it uses alt.Undefined instead
    ).configure(
        background="rgba(0, 0, 0, 0.2)" # rgba(red, green, blue, alpha) -> 0.0 is fully transparent, 1.0 is opaque
    )
    # Adding the title in properties and padding (in pixels) around the entire chart canvas, so that the titles are not very close to the edges
    props = {'title': specs['title'], 'padding':{"left": 10, "top": 10, "right": 10, "bottom": 10},} 

    # For horizontal bars/heatmap with many categoric types, the category labels can be jammed up easilly if there are more than 10
    if specs['y']['type'] == 'nominal': 
        props['height'] = alt.Step(28) # Setting each category height to 28 px each, so that the graph can be readable
    return chart.properties(**props) # retrunging the chart object with the properties set up