import openai
import json
import os
from dotenv import load_dotenv
load_dotenv()

client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def prompt_llm(question, answer):
    prompt = f"""
    [Instruction] Determine if the answer below is factually correct and consistent with Canadian immigration policy.

    [Question]: {question}
    [Answer]: {answer}

    Respond with only 'Correct' or 'Incorrect'.
    """
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return response.choices[0].message.content.strip()

def run_llm_classifier(file_in, file_out):
    with open(file_in) as f_in, open(file_out, 'w') as f_out:
        for line in f_in:
            ex = json.loads(line)
            verdict = prompt_llm(ex['question'], ex['answer'])
            ex['llm_prediction'] = 1 if verdict.lower().startswith("correct") else 0
            f_out.write(json.dumps(ex) + "\n")
