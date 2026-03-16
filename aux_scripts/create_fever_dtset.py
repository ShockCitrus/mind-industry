import re
import pandas as pd
from prompter import Prompter
from tqdm import tqdm


df = pd.read_csv("fever_transformed.csv")

INSTRUCTIONS_PATH = "templates/transform_fever.txt"
_4_INSTRUCTIONS_PATH = "templates/discrepancy_detection.txt"

# NOTE: model and host are read from config/config.yaml (llm.default section).
# To switch backends, update 'llm.default.backend' and 'llm.default.model'.
# To use a specific Ollama model, pass model_type and ensure its server is
# listed in llm.ollama.servers in config.yaml.
promopter = Prompter(
    model_type="llama3:70b-instruct")


def parse_text(text):
    # Split on the first double newline
    parts = re.split(r"\n\n", text, maxsplit=1)
    
    if len(parts) == 2:
        label = parts[0].strip()
        reason = parts[1].strip()
    else:
        label = text.strip()  # If no reason, treat entire text as label
        reason = ""

    return label, reason

counter_ok = 0
new_dataset = []
for id_row, row in tqdm(df.iterrows(), total=df.shape[0]):
    
    # ---------------------------------------------------------------------#
    # GENERATE TRIPLETS
    # ---------------------------------------------------------------------#
    with open(INSTRUCTIONS_PATH, 'r') as file: template = file.read()
    template_formatted = template.format(
        claim=row.claim,
        label=row.label,
        evidence=row.evidence
    )
    
    response, _ = prompter.prompt(question=template_formatted)
    lines = response.splitlines()
    
    question, answer1, answer2 = None, None, None

    for line in lines:
        if line.startswith("QUESTION:"):
            question = line.split("QUESTION:")[1].strip()
        elif line.startswith("ANSWER1:"):
            answer1 = line.split("ANSWER1:")[1].strip()
        elif line.startswith("ANSWER2:"):
            answer2 = line.split("ANSWER2:")[1].strip()

    #import pdb; pdb.set_trace()
    
    print("Question:", question)
    print("Answer1:", answer1)
    print("Answer2:", answer2)
    if question is None or answer1 is None or answer2 is None:
        response_split = response.split("\n")
        question = response_split[0].strip("\n").strip("QUESTION:").strip()
        answer1 = response_split[1].strip("\n").strip("ANSWER1:").strip()
        answer2 = response_split[2].strip("\n").strip("ANSWER2:").strip()
    
    # ---------------------------------------------------------------------#
    # 4. DISCREPANCY DETECTION
    # ---------------------------------------------------------------------#
    with open(_4_INSTRUCTIONS_PATH, 'r') as file: template = file.read()
    
    template_formatted = template.format(question=question, answer_1=answer1, answer_2=answer2)
    
    discrepancy, _ = prompter.prompt(question=template_formatted)
    
    if ("contradiction" in discrepancy.lower() and row.label == "REFUTES") or ("no_discrepancy" in discrepancy.lower() and row.label == "SUPPORTS"):
        counter_ok += 1
    print("DISCREPANCY:", discrepancy)
    print("LABEL:", row.label)
    print("CLAIM:", row.claim)
    print("EVIDENCE:", row.evidence)
    
    label, reason = parse_text(discrepancy)
    
    new_dataset.append({
        "claim": row.claim,
        "evidence": row.evidence,
        "label": row.label,
        "question": question,
        "answer1": answer1,
        "answer2": answer2,
        "discrepancy": label,
        "reason": reason
    })

df_new = pd.DataFrame(new_dataset)
df_new["discrepancy"] = df_new["discrepancy"].str.replace(r"NO_ DISCREPANCY", "NO_DISCREPANCY", regex=True)

def agree(row):
    if row.label == "SUPPORTS" and "no_discrepancy" in row.discrepancy.lower():
        return 1
    elif row.label == "REFUTES" and "contradiction" in row.discrepancy.lower():
        return 1
    else:
        return 0
df_new["agree"] = df_new.apply(agree, axis=1)

df_new.to_excel("fever_transformed_discrepancy.xlsx", index=False)
    
import pdb; pdb.set_trace()