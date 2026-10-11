
import os
import io
import re
import json
import contextlib
import traceback

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Allow requests from your assignment website.
# For production, restrict this to the assignment website's origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CodeRequest(BaseModel):
    code: str


class CodeResponse(BaseModel):
    error: list[int]
    result: str


def find_error_lines(code, traceback_text):
    # Get the submitted-code line number from Python's traceback.
    matches = re.findall(
        r'File "<submitted>", line (\d+)',
        traceback_text
    )
    fallback = [int(matches[-1])] if matches else []

    token = os.getenv("AIPIPE_TOKEN")

    # Use the traceback result if no AI token is configured.
    if not token:
        return fallback

    prompt = f"""
Identify the line number or line numbers in the submitted
Python code that caused the exception.

Return only JSON in this format: {{"error": [3]}}.
Line numbers start at 1.

Submitted code:
{code}

Traceback:
{traceback_text}
"""

    try:
        response = httpx.post(
            "https://aipipe.org/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {token}"
            },
            json={
                "model": "openai/gpt-4.1-nano",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "response_format": {
                    "type": "json_object"
                }
            },
            timeout=30
        )

        response.raise_for_status()
        data = response.json()

        answer = json.loads(
            data["choices"][0]["message"]["content"]
        )

        errors = answer.get("error", [])

        # Validate the returned line numbers.
        if (
            isinstance(errors, list)
            and all(
                isinstance(line, int)
                and 1 <= line <= len(code.splitlines())
                for line in errors
            )
        ):
            return errors

        return fallback

    except Exception:
        # If the AI service fails, use traceback detection.
        return fallback


@app.get("/")
def home():
    return {"message": "Code Interpreter API is running"}


@app.post(
    "/code-interpreter",
    response_model=CodeResponse
)
def code_interpreter(request: CodeRequest):
    output = io.StringIO()

    try:
        with contextlib.redirect_stdout(output):
            exec(
                compile(request.code, "<submitted>", "exec"),
                {}
            )

        return {
            "error": [],
            "result": output.getvalue()
        }

    except Exception:
        trace = traceback.format_exc()

        error_lines = find_error_lines(
            request.code,
            trace
        )

        return {
            "error": error_lines,
            "result": trace
        }
