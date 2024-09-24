import os
import base64
import re
import json

import streamlit as st
from urllib.parse import urlparse, parse_qs
import openai
from openai import AssistantEventHandler
from tools import TOOL_MAP
from typing_extensions import override
from dotenv import load_dotenv
import requests

load_dotenv() 

bubble_api_key = os.environ.get("BUBBLE_API_KEY")

hide_streamlit_style = """
            <style>
                header {visibility: hidden;}
                .streamlit-footer {display: none;}
                .st-emotion-cache-h4xjwg {display: none;}
            </style>
            """

st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def str_to_bool(str_input):
    if not isinstance(str_input, str):
        return False
    return str_input.lower() == "true"

if 'id' not in st.query_params:
    st.error("Missing URL parameter: id")
    st.stop() 

unique_id = st.query_params["id"] 
if 'initial_greeting' in st.query_params:
    initial_greeting = st.query_params["initial_greeting"]
    if initial_greeting == '':
        initial_greeting = False
else:
    initial_greeting = False

if 'openai_api_key' not in st.session_state:
    # Send a GET request to the API
    #url = "https://assistembedd.bubbleapps.io/version-test/api/1.1/wf/get-embed?id="+unique_id
    url = "https://assistor.online/api/1.1/wf/get-embed?id="+unique_id

    headers = {
        'Authorization': f'Bearer {bubble_api_key}'
    }

    # Make the request with the authorization header
    response = requests.get(url, headers=headers, timeout=10)

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the JSON response if it's available
        response = response.json()
        #st.write(response)
        st.session_state["openai_api_key"] = response["response"]["openai_key"]["openai_text"]
        st.session_state["chatGPT_assistant_id"] = response["response"]["openai_key"]["assistant_id_text"]
    else:
        st.error("Request failed with "+{response.status_code})
        st.stop()

    if 'greeted' not in st.session_state:
        st.session_state['greeted'] = True
        if initial_greeting:
            with st.chat_message("assistant"):
                st.write(initial_greeting)

# Load environment variables
instructions = os.environ.get("RUN_INSTRUCTIONS", "Instructions")
enabled_file_upload_message = os.environ.get(
    "ENABLED_FILE_UPLOAD_MESSAGE", ""
)


openaiClient = None
openaiClient = openai.OpenAI(api_key=st.session_state["openai_api_key"])
assistant_id = st.session_state["chatGPT_assistant_id"]


class EventHandler(AssistantEventHandler):
    @override
    def on_event(self, event):
        pass

    @override
    def on_text_created(self, text):
        st.session_state.current_message = ""
        with st.chat_message("Assistant"):
            st.session_state.current_markdown = st.empty()

    @override
    def on_text_delta(self, delta, snapshot):
        if snapshot.value:
            text_value = re.sub(
                r"\[(.*?)\]\s*\(\s*(.*?)\s*\)", "Download Link", snapshot.value
            )
            st.session_state.current_message = text_value
            st.session_state.current_markdown.markdown(
                st.session_state.current_message, True
            )

    @override
    def on_text_done(self, text):
        format_text = format_annotation(text)
        st.session_state.current_markdown.markdown(format_text, True)
        st.session_state.chat_log.append({"name": "assistant", "msg": format_text})

    @override
    def on_tool_call_created(self, tool_call):
        if tool_call.type == "code_interpreter":
            st.session_state.current_tool_input = ""
            with st.chat_message("Assistant"):
                st.session_state.current_tool_input_markdown = st.empty()

    @override
    def on_tool_call_delta(self, delta, snapshot):
        if 'current_tool_input_markdown' not in st.session_state:
            with st.chat_message("Assistant"):
                st.session_state.current_tool_input_markdown = st.empty()

        if delta.type == "code_interpreter":
            if delta.code_interpreter.input:
                st.session_state.current_tool_input += delta.code_interpreter.input
                input_code = f"### code interpreter\ninput:\n```python\n{st.session_state.current_tool_input}\n```"
                st.session_state.current_tool_input_markdown.markdown(input_code, True)

            if delta.code_interpreter.outputs:
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        pass

    @override
    def on_tool_call_done(self, tool_call):
        st.session_state.tool_calls.append(tool_call)
        if tool_call.type == "code_interpreter":
            if tool_call.id in [x.id for x in st.session_state.tool_calls]:
                return
            input_code = f"### code interpreter\ninput:\n```python\n{tool_call.code_interpreter.input}\n```"
            st.session_state.current_tool_input_markdown.markdown(input_code, True)
            st.session_state.chat_log.append({"name": "assistant", "msg": input_code})
            st.session_state.current_tool_input_markdown = None
            for output in tool_call.code_interpreter.outputs:
                if output.type == "logs":
                    output = f"### code interpreter\noutput:\n```\n{output.logs}\n```"
                    with st.chat_message("Assistant"):
                        st.markdown(output, True)
                        st.session_state.chat_log.append(
                            {"name": "assistant", "msg": output}
                        )
        elif (
            tool_call.type == "function"
            and self.current_run.status == "requires_action"
        ):
            with st.chat_message("Assistant"):
                msg = f"### Function Calling: {tool_call.function.name}"
                st.markdown(msg, True)
                st.session_state.chat_log.append({"name": "assistant", "msg": msg})
            tool_calls = self.current_run.required_action.submit_tool_outputs.tool_calls
            tool_outputs = []
            for submit_tool_call in tool_calls:
                tool_function_name = submit_tool_call.function.name
                tool_function_arguments = json.loads(
                    submit_tool_call.function.arguments
                )
                tool_function_output = TOOL_MAP[tool_function_name](
                    **tool_function_arguments
                )
                tool_outputs.append(
                    {
                        "tool_call_id": submit_tool_call.id,
                        "output": tool_function_output,
                    }
                )

            with openaiClient.beta.threads.runs.submit_tool_outputs_stream(
                thread_id=st.session_state.thread.id,
                run_id=self.current_run.id,
                tool_outputs=tool_outputs,
                event_handler=EventHandler(),
            ) as stream:
                stream.until_done()


def create_thread(content, file):
    return openaiClient.beta.threads.create()


def create_message(thread, content, file):
    attachments = []
    if file is not None:
        attachments.append(
            {"file_id": file.id, "tools": [{"type": "code_interpreter"}, {"type": "file_search"}]}
        )
    openaiClient.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=content, attachments=attachments
    )


def create_file_link(file_name, file_id):
    content = openaiClient.files.content(file_id)
    content_type = content.response.headers["content-type"]
    b64 = base64.b64encode(content.text.encode(content.encoding)).decode()
    link_tag = f'<a href="data:{content_type};base64,{b64}" download="{file_name}">Download Link</a>'
    return link_tag


def format_annotation(text):
    citations = []
    text_value = text.value
    for index, annotation in enumerate(text.annotations):
        text_value = text_value.replace(annotation.text, f" [{index}]")

        if file_citation := getattr(annotation, "file_citation", None):
            cited_file = openaiClient.files.retrieve(file_citation.file_id)
            citations.append(
                f"[{index}] {file_citation.quote} from {cited_file.filename}"
            )
        elif file_path := getattr(annotation, "file_path", None):
            link_tag = create_file_link(
                annotation.text.split("/")[-1],
                file_path.file_id,
            )
            text_value = re.sub(r"\[(.*?)\]\s*\(\s*(.*?)\s*\)", link_tag, text_value)
    text_value += "\n\n" + "\n".join(citations)
    return text_value


def run_stream(user_input, file, selected_assistant_id):
    if "thread" not in st.session_state:
        st.session_state.thread = create_thread(user_input, file)
    create_message(st.session_state.thread, user_input, file)
    with openaiClient.beta.threads.runs.stream(
        thread_id=st.session_state.thread.id,
        assistant_id=selected_assistant_id,
        event_handler=EventHandler(),
    ) as stream:
        stream.until_done()


def handle_uploaded_file(uploaded_file):
    file = openaiClient.files.create(file=uploaded_file, purpose="assistants")
    return file


def render_chat():
    for chat in st.session_state.chat_log:
        with st.chat_message(chat["name"]):
            st.markdown(chat["msg"], True)


if "tool_call" not in st.session_state:
    st.session_state.tool_calls = []

if "chat_log" not in st.session_state:
    st.session_state.chat_log = []

if "in_progress" not in st.session_state:
    st.session_state.in_progress = False


def disable_form():
    st.session_state.in_progress = True


def reset_chat():
    st.session_state.chat_log = []
    st.session_state.in_progress = False


def load_chat_screen(assistant_id, assistant_title):
    if enabled_file_upload_message:
        uploaded_file = st.sidebar.file_uploader(
            enabled_file_upload_message,
            type=[
                "txt",
                "pdf",
                "png",
                "jpg",
                "jpeg",
                "csv",
                "json",
                "geojson",
                "xlsx",
                "xls",
            ],
            disabled=st.session_state.in_progress,
        )
    else:
        uploaded_file = None

    user_msg = st.chat_input(
        "Message",
        on_submit=disable_form,
        disabled=st.session_state.in_progress,
        max_chars=1024,

    )
    if user_msg:
        render_chat()
        with st.chat_message("user"):
            st.markdown(user_msg, True)
        st.session_state.chat_log.append({"name": "user", "msg": user_msg})

        file = None
        if uploaded_file is not None:
            file = handle_uploaded_file(uploaded_file)
        run_stream(user_msg, file, assistant_id)
        st.session_state.in_progress = False
        st.session_state.tool_call = None
        st.rerun()

    render_chat()


def main():
    # Check if multi-agent settings are defined
    multi_agents = os.environ.get("OPENAI_ASSISTANTS", None)
    single_agent_id = os.environ.get("ASSISTANT_ID", None)
    single_agent_title = os.environ.get("ASSISTANT_TITLE", "Assistants API UI")

    if assistant_id:
        load_chat_screen(assistant_id, single_agent_title)    
    else:
        st.error("No assistant configurations defined in environment variables.")


if __name__ == "__main__":
    main()
