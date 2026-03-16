import re
import pandas as pd
from prompter import Prompter
from tqdm import tqdm

### Load DPLACE data
df_vars = pd.read_csv("dplace-data/datasets/EA/variables.csv")
df_vars = df_vars[df_vars.type == "Categorical"][["id", "category", "title", "definition"]]
df_codes = pd.read_csv("dplace-data/datasets/EA/codes.csv")

#### this is for the generation of v1 ####
df_vars_v2_orig = df_vars.copy()
df_vars_v2_orig["codes"] = df_vars_v2_orig["id"].apply(lambda x: [code for code in df_codes[df_codes.var_id == x]["description"].values.tolist()])
df_vars["codes"] = df_vars["id"].apply(lambda x: [code for code in df_codes[df_codes.var_id == x]["description"].values.tolist() if code != "Missing data"])
df_vars = df_vars[~df_vars['codes'].apply(lambda x: any("Missing data" in str(item) for item in x))]
df_vars = df_vars.dropna(subset=['codes'])
v1_dplace = df_vars.sample(n=50, random_state=1234)

#### generating v2 ####
missing_candidates = df_vars_v2_orig[df_vars_v2_orig["codes"].astype(str).str.contains("missing data|Insufficient information or not coded", case=False, na=False)]
missing_candidates = missing_candidates[~missing_candidates["id"].isin(v1_dplace["id"])].dropna(subset=['codes'])
remaining_df = df_vars[~df_vars["id"].isin(v1_dplace["id"])]
add_cultural_candidates = remaining_df.sample(n=5, random_state=5678)

df_dplace = pd.concat([add_cultural_candidates, add_cultural_candidates])
print(f"Generating additional {df_dplace.shape[0]} rows for v2")

### Load FEVER data
#df_fever = pd.read_csv("FEVER-DPLACE-Q_v1.xlsx")

#### Load V1 ####
df_v1 = pd.read_excel("FEVER-DPLACE-Q_v1.xlsx")
## Corrected wrong claims
target_claim = "Political integration of the society with neighbouring communities and/or a larger state; this is the version that appeared in Murdock (1957)'s World Ethnographic Sample (WES)."

# Update the "label" column where "claim" matches the target value
df_v1.loc[df_v1["claim"] == target_claim, "label"] = "NOT_ENOUGH_INFO"

### TEMPLATES
DPLACE_INSTRUCTIONS_PATH = "templates/transform_dplace.txt"
FEVER_INSTRUCTIONS_PATH = "templates/transform_fever.txt"
_4_INSTRUCTIONS_PATH = "templates/discrepancy_detection.txt"

### Prompter
# NOTE: model and host are read from config/config.yaml (llm.default section).
# To switch backends, update 'llm.default.backend' and 'llm.default.model'.
prompter_create = Prompter(
    model_type="gpt-4o-2024-08-06")

prompter_disc = Prompter(
    model_type="gpt-4o-2024-08-06")

counter_ok = 0
new_dataset = []
for id_row, row in tqdm(df_dplace.iterrows(), total=df_dplace.shape[0]):
    
    # ---------------------------------------------------------------------#
    # GENERATE TRIPLETS
    # ---------------------------------------------------------------------#
    with open(DPLACE_INSTRUCTIONS_PATH, 'r') as file: template = file.read()
    template_formatted = template.format(
        definition=row.definition,
        example1=row.codes[0],
        example2=row.codes[1]
    )
    
    response, _ = prompter_create.prompt(question=template_formatted)
    lines = response.splitlines()
    
    question, answer1, answer2 = None, None, None

    for line in lines:
        if line.startswith("QUESTION:"):
            question = line.split("QUESTION:")[1].strip()
        elif line.startswith("ANSWER1:"):
            answer1 = line.split("ANSWER1:")[1].strip()
        elif line.startswith("ANSWER2:"):
            answer2 = line.split("ANSWER2:")[1].strip()
    
    print("Question:", question)
    print("Answer1:", answer1)
    print("Answer2:", answer2)
    if question is None or answer1 is None or answer2 is None:
        response_split = response.split("\n")
        question = response_split[0].strip("\n").strip("QUESTION:").strip()
        answer1 = response_split[1].strip("\n").strip("ANSWER1:").strip()
        answer2 = response_split[2].strip("\n").strip("ANSWER2:").strip()
    
    if row.codes[0] == "Missing data" or row.codes[1] == "Missing data":
        label = "NOT_ENOUGH_INFO"
    else:
        label = "CULTURAL_DISCREPANCY"
    print(row.codes[0], row.codes[1], label)
    #import pdb; pdb.set_trace()  
    new_dataset.append({
        "claim": row.definition,
        "evidence": row.codes[:2],
        "label": label,
        "question": question,
        "answer1": answer1,
        "answer2": answer2,
    })
    import pdb; pdb.set_trace()
    
"""
for id_row, row in tqdm(df_fever.iterrows(), total=df_fever.shape[0]):
    
    # ---------------------------------------------------------------------#
    # GENERATE TRIPLETS
    # ---------------------------------------------------------------------#
    with open(FEVER_INSTRUCTIONS_PATH, 'r') as file: template = file.read()
    template_formatted = template.format(
        claim=row.claim,
        label=row.label,
        evidence=row.evidence
    )
    
    response, _ = prompter_create.prompt(question=template_formatted)
    lines = response.splitlines()
    
    question, answer1, answer2 = None, None, None

    for line in lines:
        if line.startswith("QUESTION:"):
            question = line.split("QUESTION:")[1].strip()
        elif line.startswith("ANSWER1:"):
            answer1 = line.split("ANSWER1:")[1].strip()
        elif line.startswith("ANSWER2:"):
            answer2 = line.split("ANSWER2:")[1].strip()
    
    print("Question:", question)
    print("Answer1:", answer1)
    print("Answer2:", answer2)
    if question is None or answer1 is None or answer2 is None:
        response_split = response.split("\n")
        question = response_split[0].strip("\n").strip("QUESTION:").strip()
        answer1 = response_split[1].strip("\n").strip("ANSWER1:").strip()
        answer2 = response_split[2].strip("\n").strip("ANSWER2:").strip()
    
    new_dataset.append({
        "claim": row.claim,
        "evidence": row.evidence,
        "label": row.label,
        "question": question,
        "answer1": answer1,
        "answer2": answer2,
        #"reason": reason
    })
"""

df_new = pd.DataFrame(new_dataset)
df_new_v2 = pd.concat([df_v1, df_new])

df_new_v2["label"] = df_new_v2["label"].apply(lambda x : x.replace("REFUTES", "CONTRADICTION"))
df_new_v2["label"] = df_new_v2["label"].apply(lambda x : x.replace("SUPPORTS", "NO_DISCREPANCY"))

df_new_v2.to_excel("FEVER-DPLACE-Q_v2.xlsx", index=False)