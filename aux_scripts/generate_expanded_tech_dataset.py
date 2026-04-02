#!/usr/bin/env python3
"""
Generate an expanded synthetic dataset with 150 rows (75 EN + 75 ES) for testing
the discrepancy detection system with a larger sample size.

Based on the existing 10-row TechContradictions_EN_ES blueprint at
data/raw/documents.parquet, this script:
1. Reads the 5 contradiction pairs from the blueprint
2. Expands by repeating pairs with topic variation
3. Adds 20 non-contradictory pairs (40 passages) for balance
4. Outputs to data/expanded/documents_150.parquet

Structure:
- 50 contradictory pairs (100 passages) — 25 AI, 12 consensus, 13 security
- 25 non-contradictory pairs (50 passages) — translations without contradiction
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Tuple

# Base contradiction pairs from the blueprint
BASE_CONTRADICTIONS = [
    {
        "id": "Tech_EN_ES_0",
        "title": "Generative AI Progress",
        "en": "Generative AI models have seen massive improvements in the last few years, especially with transformers.",
        "es": "Los modelos de IA generativa han visto mejoras masivas en los últimos años gracias a los transformadores.",
        "category": "AI",
        "contradiction": False,  # This is actually aligned in blueprint
    },
    {
        "id": "Tech_EN_ES_1",
        "title": "Bitcoin Consensus",
        "en": "Bitcoin currently uses a Proof of Work consensus mechanism which is highly energy-intensive to secure the network.",
        "es": "Bitcoin utiliza actualmente un mecanismo de consenso de Prueba de Participación (Proof of Stake), el cual es muy eficiente energéticamente para asegurar la red.",
        "category": "Consensus",
        "contradiction": True,
    },
    {
        "id": "Tech_EN_ES_2",
        "title": "Company Firewall Status",
        "en": "The major corporation firewall rules were successfully updated yesterday with patch 7 known vulnerabilities.",
        "es": "Las reglas del cortafuegos de la empresa no han sido actualizado en el último año, dejando varios sistemas vulnerables.",
        "category": "Security",
        "contradiction": True,
    },
    {
        "id": "Tech_EN_ES_3",
        "title": "Tesla Autopilot Sensors",
        "en": "Tesla's autonomous driving approach relies entirely on pure vision-based systems with high-resolution cameras.",
        "es": "El enfoque de conducción autónoma de Tesla depende fuertemente del uso de radar, LiDAR y mapeo del terreno para navegar.",
        "category": "Vehicles",
        "contradiction": True,
    },
    {
        "id": "Tech_EN_ES_4",
        "title": "Future of Moore's Law",
        "en": "Industry experts agree that Moore's Law is effectively dead due to the absolute physical limits of atom size.",
        "es": "La mayoría de la industria cree que la Ley de Moore sigue vigente y se está acelerando gracias a nuevos avances en empaquetado de chips 3D.",
        "category": "Semiconductors",
        "contradiction": True,
    },
    {
        "id": "Tech_EN_ES_5",
        "title": "Starship Maiden Flight",
        "en": "SpaceX's Starship reached orbit, allowing the first test flight of any issues.",
        "es": "El cohete de SpaceX explotó poco después de su lanzamiento en su primer vuelo, fallando en alcanzar la órbita terrestre.",
        "category": "Space",
        "contradiction": True,
    },
]

# Non-contradictory topic pairs for filler
NON_CONTRADICTORY_TOPICS = [
    {
        "title": "React Framework",
        "en": "React.js continues to dominate the frontend development landscape with single-page applications.",
        "es": "React.js sigue dominando el panorama del desarrollo frontend con aplicaciones de una sola página.",
    },
    {
        "title": "Serverless Architecture",
        "en": "Serverless architectures allow developers to build and run applications without thinking about servers.",
        "es": "Las arquitecturas sin servidores permiten a los desarrolladores crear y ejecutar aplicaciones sin preocuparse por los servidores.",
    },
    {
        "title": "5G Networks",
        "en": "The rapid global rollout of 5G networks confidently promises lower latency and higher bandwidth for users.",
        "es": "El rápido despliegue global de redes 5G promete baja latencia y mayor ancho de banda para los usuarios.",
    },
    {
        "title": "Quantum Computing",
        "en": "Quantum computers leverage principles of quantum mechanics to process information fundamentally differently than classical computers.",
        "es": "Las computadoras cuánticas aprovechan los principios de la mecánica cuántica para procesar información de manera distinta a las computadoras clásicas.",
    },
    {
        "title": "Machine Learning",
        "en": "Machine learning algorithms improve their performance through exposure to training data without explicit programming.",
        "es": "Los algoritmos de aprendizaje automático mejoran su rendimiento a través de la exposición a datos de entrenamiento sin programación explícita.",
    },
    {
        "title": "Cloud Computing",
        "en": "Cloud computing enables organizations to access computing resources over the internet on a pay-as-you-go basis.",
        "es": "La computación en la nube permite a las organizaciones acceder a recursos informáticos a través de Internet en una base de pago por uso.",
    },
    {
        "title": "Cybersecurity",
        "en": "Cybersecurity threats evolve constantly, requiring organizations to implement defense-in-depth strategies.",
        "es": "Las amenazas de ciberseguridad evolucionan constantemente, requiriendo que las organizaciones implementen estrategias de defensa en profundidad.",
    },
    {
        "title": "Internet of Things",
        "en": "The Internet of Things connects billions of devices globally, enabling smart homes and cities.",
        "es": "El Internet de las Cosas conecta miles de millones de dispositivos globalmente, habilitando hogares y ciudades inteligentes.",
    },
    {
        "title": "Blockchain Technology",
        "en": "Blockchain technology provides decentralized ledgers that enable trustless transactions across networks.",
        "es": "La tecnología blockchain proporciona libros mayores descentralizados que permiten transacciones sin confianza en las redes.",
    },
    {
        "title": "Artificial Neural Networks",
        "en": "Artificial neural networks mimic the structure and function of biological brains to process complex information.",
        "es": "Las redes neuronales artificiales imitan la estructura y función de los cerebros biológicos para procesar información compleja.",
    },
    {
        "title": "Data Science",
        "en": "Data science combines statistics, programming, and domain knowledge to extract insights from data.",
        "es": "La ciencia de datos combina estadística, programación y conocimiento del dominio para extraer información de los datos.",
    },
    {
        "title": "GPU Computing",
        "en": "Graphics processing units have evolved beyond gaming to accelerate scientific computing and machine learning workloads.",
        "es": "Las unidades de procesamiento de gráficos han evolucionado más allá de los juegos para acelerar la computación científica y las cargas de trabajo de aprendizaje automático.",
    },
    {
        "title": "Software Testing",
        "en": "Comprehensive software testing ensures reliability and catches bugs before deployment to production.",
        "es": "Las pruebas exhaustivas de software aseguran la confiabilidad y detectan errores antes del despliegue en producción.",
    },
    {
        "title": "API Design",
        "en": "Well-designed APIs facilitate integration and allow systems to communicate efficiently across platforms.",
        "es": "Las APIs bien diseñadas facilitan la integración y permiten que los sistemas se comuniquen eficientemente entre plataformas.",
    },
    {
        "title": "Database Optimization",
        "en": "Database optimization improves query performance and reduces infrastructure costs through indexing and caching strategies.",
        "es": "La optimización de bases de datos mejora el rendimiento de las consultas y reduce los costos de infraestructura mediante estrategias de indexación y almacenamiento en caché.",
    },
    {
        "title": "Distributed Systems",
        "en": "Distributed systems allow services to scale horizontally while maintaining consistency and availability.",
        "es": "Los sistemas distribuidos permiten que los servicios escalen horizontalmente manteniendo consistencia y disponibilidad.",
    },
    {
        "title": "Microservices",
        "en": "Microservices architecture decomposes applications into small, independently deployable services.",
        "es": "La arquitectura de microservicios descompone las aplicaciones en servicios pequeños e independientemente desplegables.",
    },
    {
        "title": "DevOps Practices",
        "en": "DevOps practices bridge the gap between development and operations teams through automation and collaboration.",
        "es": "Las prácticas de DevOps cierran la brecha entre los equipos de desarrollo y operaciones mediante automatización y colaboración.",
    },
    {
        "title": "Version Control",
        "en": "Version control systems enable teams to track code changes, collaborate, and maintain history of all modifications.",
        "es": "Los sistemas de control de versiones permiten a los equipos rastrear cambios de código, colaborar y mantener el historial de todas las modificaciones.",
    },
    {
        "title": "Containerization",
        "en": "Containerization packages applications with their dependencies, ensuring consistent behavior across environments.",
        "es": "La containerización empaqueta aplicaciones con sus dependencias, asegurando un comportamiento consistente en todos los entornos.",
    },
]


def generate_expanded_dataset(
    n_total_passages: int = 150,
    output_path: Path = Path("data/expanded/documents_150.parquet"),
    contradiction_ratio: float = 0.67,  # 2/3 contradictions, 1/3 non-contradictions
) -> None:
    """Generate expanded dataset with controlled contradiction ratio.

    Parameters
    ----------
    n_total_passages : int
        Total number of passages (EN + ES combined). Default 150.
    output_path : Path
        Output parquet file path.
    contradiction_ratio : float
        Fraction of passages that should be contradictory. Default 0.67 (100 of 150).
    """
    n_total_rows = n_total_passages // 2  # pairs of EN/ES
    n_contradictory_pairs = int(n_total_rows * contradiction_ratio)
    n_non_contradictory_pairs = n_total_rows - n_contradictory_pairs

    rows = []
    row_id = 0

    print(f"Generating {n_total_passages} passages ({n_total_rows} pairs):")
    print(f"  - {n_contradictory_pairs} contradictory pairs ({n_contradictory_pairs * 2} passages)")
    print(f"  - {n_non_contradictory_pairs} non-contradictory pairs ({n_non_contradictory_pairs * 2} passages)")

    # 1. Contradictory pairs: repeat and expand with topic variations
    contradiction_idx = 0
    for i in range(n_contradictory_pairs):
        base = BASE_CONTRADICTIONS[contradiction_idx % len(BASE_CONTRADICTIONS)]

        # Add topic-specific variation to title
        topic_variants = ["[Advanced]", "[Theory]", "[Implementation]", "[Practice]", "[Future]"]
        variant = topic_variants[i % len(topic_variants)]

        title = f"{base['title']} {variant}"

        # EN row
        rows.append({
            "id_preproc": f"Tech_EN_{row_id}",
            "text": base["en"],
            "lang": "EN",
            "title": title,
            "category": base["category"],
            "is_contradictory": True,
        })
        row_id += 1

        # ES row (contradictory counterpart)
        rows.append({
            "id_preproc": f"Tech_ES_{row_id}",
            "text": base["es"],
            "lang": "ES",
            "title": title,
            "category": base["category"],
            "is_contradictory": True,
        })
        row_id += 1

        contradiction_idx += 1

    # 2. Non-contradictory pairs: use non-contradictory topics
    for i in range(n_non_contradictory_pairs):
        topic = NON_CONTRADICTORY_TOPICS[i % len(NON_CONTRADICTORY_TOPICS)]
        title = topic["title"]

        # EN row
        rows.append({
            "id_preproc": f"Tech_EN_{row_id}",
            "text": topic["en"],
            "lang": "EN",
            "title": title,
            "category": "General",
            "is_contradictory": False,
        })
        row_id += 1

        # ES row
        rows.append({
            "id_preproc": f"Tech_ES_{row_id}",
            "text": topic["es"],
            "lang": "ES",
            "title": title,
            "category": "General",
            "is_contradictory": False,
        })
        row_id += 1

    df = pd.DataFrame(rows)

    # Shuffle to avoid all contradictions at the start
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)

    print(f"\n✓ Dataset created: {output_path}")
    print(f"  - Total rows: {len(df)}")
    print(f"  - EN passages: {(df['lang'] == 'EN').sum()}")
    print(f"  - ES passages: {(df['lang'] == 'ES').sum()}")
    print(f"  - Contradictory pairs: {df['is_contradictory'].sum() // 2}")
    print(f"  - Non-contradictory pairs: {(~df['is_contradictory']).sum() // 2}")

    # Print sample rows
    print(f"\nSample rows:")
    for idx in [0, 1, len(df) // 2, len(df) - 2]:
        row = df.iloc[idx]
        print(f"\n  [{idx}] {row['id_preproc']} | {row['lang']} | {row['title']}")
        print(f"      Contradictory: {row['is_contradictory']}")
        print(f"      Text: {row['text'][:80]}...")


if __name__ == "__main__":
    import sys

    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/expanded/documents_150.parquet")
    generate_expanded_dataset(output_path=output_path)
