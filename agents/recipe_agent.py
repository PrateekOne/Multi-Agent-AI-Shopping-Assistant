from llm_client import send_prompt_to_llm
import json


def expand_recipe(prompt):
    llm_prompt = f"""
    Convert this food into grocery items.

    Input: {prompt}

    Return JSON list:
    [
      {{"name": "...", "quantity": "..."}},
      ...
    ]

    Only ingredients. No explanation.
    """

    response = send_prompt_to_llm(llm_prompt)

    try:
        return json.loads(response)
    except:
        return [{"name": prompt}]