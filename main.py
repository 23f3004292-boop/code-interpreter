
import os
import sys
import io
import contextlib
import traceback

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class CodeRequest(BaseModel):
    code: str


class CodeResponse(BaseModel):
    error: list[int]
    result: str



def find_error_lines(code, traceback_text):
    import json
    import re

    # Find the submitted-code line from the Python traceback.
    matches = re.findall(
        r'File "<submitted>", line (\d+)',
        traceback_text
    )
    fallback = [int(matches[-1])] if matches else []

    token = os.getenv("AIPIPE_TOKEN")
    if not token:
        return fallback

    prompt = f"""
Identify the line number(s) in the submitted Python code
that caused the exception.
Return only JSON like {{"error": [3]}}.
Line numbers start at 1.

Code:
{code}

Traceback:
{traceback_text}
"""

    try:
        response = httpx.post(
            "https://aipipe.org/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": "openai/gpt-4.1-nano",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"}
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        answer = json.loads(
            data["choices"][0]["message"]["content"]
        )
        errors = answer.get("error", [])
        return errors if errors else fallback

    except Exception:
        return fallback



@app.post("/code-interpreter", response_model=CodeResponse)
def code_interpreter(request: CodeRequest):
    output = io.StringIO()
    error_lines = []

    try:
        with contextlib.redirect_stdout(output):
            exec(
                compile(request.code, "<submitted>", "exec"),
                {}
            )
        result = output.getvalue()
        return {"error": [], "result": result}

    except Exception:
        trace = traceback.format_exc()
        error_lines = find_error_lines(request.code, trace)
        return {"error": error_lines, "result": trace}
