import pandas as pd
import os

# Define the dataset
data = [
    # 1. AI (Matching)
    {"id_preproc": "Tech_EN_ES_0", "lang": "EN", "title": "Generative AI Progress", "text": "Generative AI models have seen massive improvements in the last few years, especially with transformers."},
    {"id_preproc": "Tech_EN_ES_1", "lang": "ES", "title": "Progreso de la IA Generativa", "text": "Los modelos de IA generativa han visto mejoras masivas en los últimos años, especialmente con los transformadores."},
    
    # 2. Quantum Computing (Matching)
    {"id_preproc": "Tech_EN_ES_2", "lang": "EN", "title": "Quantum Supremacy", "text": "Quantum computers leverage principles of quantum mechanics to process information fundamentally differently than classical computers."},
    {"id_preproc": "Tech_EN_ES_3", "lang": "ES", "title": "Supremacía Cuántica", "text": "Los ordenadores cuánticos aprovechan los principios de la mecánica cuántica para procesar información de forma fundamentalmente distinta a los ordenadores clásicos."},
    
    # 3. Blockchain (Contradiction 1)
    {"id_preproc": "Tech_EN_ES_4", "lang": "EN", "title": "Bitcoin Consensus", "text": "Bitcoin currently uses a Proof of Work consensus mechanism which is highly energy-intensive to secure the network."},
    {"id_preproc": "Tech_EN_ES_5", "lang": "ES", "title": "Consenso de Bitcoin", "text": "Bitcoin utiliza actualmente un mecanismo de consenso de Prueba de Participación (Proof of Stake), el cual es muy eficiente energéticamente para asegurar la red."},
    
    # 4. Web Dev (Matching)
    {"id_preproc": "Tech_EN_ES_6", "lang": "EN", "title": "Frontend Frameworks", "text": "React and Vue.js continue to dominate the frontend development landscape for single page applications."},
    {"id_preproc": "Tech_EN_ES_7", "lang": "ES", "title": "Frameworks de Frontend", "text": "React y Vue.js siguen dominando el panorama del desarrollo frontend para aplicaciones de una sola página."},
    
    # 5. Cyber Security (Contradiction 2)
    {"id_preproc": "Tech_EN_ES_8", "lang": "EN", "title": "Company Firewall Status", "text": "The main corporate firewall rules were successfully updated yesterday to patch all known vulnerabilities."},
    {"id_preproc": "Tech_EN_ES_9", "lang": "ES", "title": "Estado del Cortafuegos de la Empresa", "text": "Las reglas principales del cortafuegos corporativo no han sido actualizadas en el último año, dejando los sistemas vulnerables."},
    
    # 6. Cloud Computing (Matching)
    {"id_preproc": "Tech_EN_ES_10", "lang": "EN", "title": "Serverless Architectures", "text": "Serverless architectures allow developers to build and run applications without thinking about servers."},
    {"id_preproc": "Tech_EN_ES_11", "lang": "ES", "title": "Arquitecturas Serverless", "text": "Las arquitecturas serverless permiten a los desarrolladores crear y ejecutar aplicaciones sin preocuparse por los servidores."},
    
    # 7. 5G Networks (Matching)
    {"id_preproc": "Tech_EN_ES_12", "lang": "EN", "title": "5G Expansion", "text": "The rapid global rollout of 5G networks confidently promises lower latency and higher bandwidth for users."},
    {"id_preproc": "Tech_EN_ES_13", "lang": "ES", "title": "Expansión 5G", "text": "El despliegue de las redes 5G promete menor latencia y mayor ancho de banda para los usuarios móviles a nivel global."},
    
    # 8. Autonomous Vehicles (Contradiction 3)
    {"id_preproc": "Tech_EN_ES_14", "lang": "EN", "title": "Tesla Autopilot Sensors", "text": "Tesla's autonomous driving approach relies entirely on purely vision-based systems with high-resolution cameras, having abandoned radar and LiDAR entirely."},
    {"id_preproc": "Tech_EN_ES_15", "lang": "ES", "title": "Sensores del Autopilot de Tesla", "text": "El enfoque de conducción autónoma de Tesla depende fuertemente del uso de sensores LiDAR para mapear el entorno y asegurar una navegación segura."},
    
    # 9. Semiconductors (Contradiction 4)
    {"id_preproc": "Tech_EN_ES_16", "lang": "EN", "title": "Future of Moore's Law", "text": "Industry experts agree that Moore's Law is effectively dead due to the absolute physical limits of silicon atom size."},
    {"id_preproc": "Tech_EN_ES_17", "lang": "ES", "title": "El futuro de la Ley de Moore", "text": "Los expertos de la industria coinciden en que la Ley de Moore sigue vigente y se está acelerando gracias a los nuevos avances en el empaquetado de chips 3D."},
    
    # 10. Space Tech (Contradiction 5)
    {"id_preproc": "Tech_EN_ES_18", "lang": "EN", "title": "Starship Maiden Flight", "text": "SpaceX's Starship successfully reached orbit, completing all stated objectives on its highly anticipated maiden flight without any issues."},
    {"id_preproc": "Tech_EN_ES_19", "lang": "ES", "title": "Vuelo Inaugural de Starship", "text": "La nave Starship de SpaceX explotó poco después del despegue en su esperado primer vuelo, fallando en alcanzar la órbita terrestre."}
]

df = pd.DataFrame(data)

# Reorder columns to match original: id_preproc, text, lang, title
df = df[['id_preproc', 'text', 'lang', 'title']]

print(f"Dataset generated with {len(df)} records.")
print(df.info())

# Ensure output directory exists
out_dir = 'Tech_EN_ES_temp'
os.makedirs(out_dir, exist_ok=True)
df.to_parquet(os.path.join(out_dir, 'dataset'), engine='pyarrow')
print(f"Dataset saved to {out_dir}/dataset")
