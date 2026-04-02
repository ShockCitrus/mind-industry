#!/usr/bin/env python3
"""
Generate a brand new synthetic dataset with fresh contradictions (not reused from blueprint).
Focuses on 5 distinct tech topics with clear category separation.

Topics:
1. Cloud Infrastructure — distributed systems, deployment models
2. Data Analytics — big data, processing frameworks
3. Web Security — SSL/TLS, authentication protocols
4. Mobile Development — cross-platform frameworks
5. DevOps & Deployment — containerization, orchestration

Each topic has 10 contradictory pairs (20 passages) + filler non-contradictions.
Total: 150 passages (75 pairs) with 50 contradictions + 25 aligned pairs.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict

# Topic 1: Cloud Infrastructure
CLOUD_CONTRADICTIONS = [
    {
        "title": "Kubernetes Deployment Model",
        "en": "Kubernetes automatically scales pod replicas based on CPU utilization metrics to handle traffic spikes.",
        "es": "Kubernetes requiere configuración manual de cada réplica de pod para manejar picos de tráfico.",
        "topic": "Cloud Infrastructure",
    },
    {
        "title": "AWS Lambda Cold Starts",
        "en": "AWS Lambda functions experience significant cold start latency when invoked after extended idle periods.",
        "es": "AWS Lambda mantiene funciones calientes permanentemente, eliminando completamente la latencia de inicio.",
        "topic": "Cloud Infrastructure",
    },
    {
        "title": "Multi-Cloud Strategy",
        "en": "Multi-cloud architecture increases vendor lock-in risk and complicates infrastructure management.",
        "es": "La arquitectura multi-cloud reduce el riesgo de bloqueo del proveedor y simplifica la gestión.",
        "topic": "Cloud Infrastructure",
    },
    {
        "title": "Container Orchestration Overhead",
        "en": "Container orchestration platforms add minimal performance overhead compared to bare metal deployment.",
        "es": "Los orquestadores de contenedores añaden sobrecarga de rendimiento significativa en comparación con metal desnudo.",
        "topic": "Cloud Infrastructure",
    },
    {
        "title": "Serverless Cost Model",
        "en": "Serverless architectures are always cheaper than traditional servers due to pay-per-invocation pricing.",
        "es": "Las arquitecturas sin servidor pueden ser más caras que servidores tradicionales para cargas de trabajo constantes.",
        "topic": "Cloud Infrastructure",
    },
    {
        "title": "Edge Computing Latency",
        "en": "Edge computing reduces latency by processing data at network edges instead of centralized cloud data centers.",
        "es": "El edge computing aumenta la latencia porque los datos deben enviarse a centros de datos centralizados para procesamiento.",
        "topic": "Cloud Infrastructure",
    },
    {
        "title": "VPC Network Isolation",
        "en": "VPCs provide complete isolation between different customer environments at the network layer.",
        "es": "Las VPCs no proporcionan aislamiento total y los datos pueden cruzarse entre entornos de clientes diferentes.",
        "topic": "Cloud Infrastructure",
    },
    {
        "title": "Spot Instances Reliability",
        "en": "Spot instances in cloud providers are interrupted randomly without warning, making them unreliable.",
        "es": "Las instancias de spot proporcionan garantías de disponibilidad del 99.9% con notificación previa de interrupciones.",
        "topic": "Cloud Infrastructure",
    },
    {
        "title": "Database Sharding Strategy",
        "en": "Horizontal sharding increases query complexity and operational overhead when joining across shards.",
        "es": "El sharding horizontal simplifica las consultas y reduce la complejidad operativa del almacenamiento distribuido.",
        "topic": "Cloud Infrastructure",
    },
    {
        "title": "Service Mesh Adoption",
        "en": "Service meshes like Istio eliminate the need for application-level retry logic and circuit breakers.",
        "es": "Los service meshes requieren que las aplicaciones implementen su propia lógica de reintentos y disyuntores.",
        "topic": "Cloud Infrastructure",
    },
]

# Topic 2: Data Analytics
DATA_ANALYTICS_CONTRADICTIONS = [
    {
        "title": "MapReduce Performance",
        "en": "MapReduce is significantly slower than modern distributed SQL engines for analytical queries.",
        "es": "MapReduce proporciona mejor rendimiento que los motores SQL distribuidos para consultas analíticas.",
        "topic": "Data Analytics",
    },
    {
        "title": "Data Lake vs Data Warehouse",
        "en": "Data lakes require strict schema enforcement, while data warehouses allow schema-on-read flexibility.",
        "es": "Los data lakes permiten flexibilidad schema-on-read, mientras que los almacenes requieren esquemas estrictos.",
        "topic": "Data Analytics",
    },
    {
        "title": "Columnar Storage Benefits",
        "en": "Columnar storage formats dramatically reduce query time for analytical workloads by 10-100x.",
        "es": "El almacenamiento en columnas ofrece negligibles mejoras en el tiempo de consulta para cargas analíticas.",
        "topic": "Data Analytics",
    },
    {
        "title": "Real-time Streaming Latency",
        "en": "Apache Kafka can achieve sub-100ms end-to-end latency for real-time data streaming.",
        "es": "Kafka tiene latencias mínimas de 5-10 segundos para datos en tiempo real debido a su batching interno.",
        "topic": "Data Analytics",
    },
    {
        "title": "Data Deduplication",
        "en": "Deduplicating data in Hadoop can reduce storage size by 50-90% depending on the dataset.",
        "es": "La deduplicación de datos en Hadoop reduce el tamaño en menos del 5% para la mayoría de datasets.",
        "topic": "Data Analytics",
    },
    {
        "title": "OLTP vs OLAP Optimization",
        "en": "OLTP and OLAP workloads require fundamentally different database optimization strategies.",
        "es": "OLTP y OLAP usan las mismas estrategias de optimización, diferenciándose solo en volumen de datos.",
        "topic": "Data Analytics",
    },
    {
        "title": "Spark Memory Management",
        "en": "Apache Spark's in-memory processing makes it 100x faster than MapReduce for iterative algorithms.",
        "es": "El procesamiento en memoria de Spark solo proporciona mejora de 2-3x sobre MapReduce en casos especiales.",
        "topic": "Data Analytics",
    },
    {
        "title": "Data Pipeline Orchestration",
        "en": "DAG-based orchestration tools like Airflow guarantee exactly-once semantics for data processing.",
        "es": "Los orquestadores basados en DAG como Airflow no garantizan semántica exactly-once sin configuración adicional.",
        "topic": "Data Analytics",
    },
    {
        "title": "Feature Engineering Automation",
        "en": "Automated feature engineering can discover complex patterns that manual engineering misses.",
        "es": "La ingeniería manual de características supera consistentemente los enfoques automatizados.",
        "topic": "Data Analytics",
    },
    {
        "title": "Data Catalog Standards",
        "en": "Data catalogs with metadata management reduce data discovery time from weeks to minutes.",
        "es": "Los catálogos de datos añaden complejidad y aumentan el tiempo de descubrimiento en lugar de reducirlo.",
        "topic": "Data Analytics",
    },
]

# Topic 3: Web Security
WEB_SECURITY_CONTRADICTIONS = [
    {
        "title": "TLS 1.3 Performance",
        "en": "TLS 1.3 eliminates the extra round trip in the TLS handshake, improving latency over TLS 1.2.",
        "es": "TLS 1.3 requiere round trips adicionales en el handshake en comparación con TLS 1.2.",
        "topic": "Web Security",
    },
    {
        "title": "HTTPS Adoption Impact",
        "en": "HTTPS adoption has increased from 30% to 90%+ of websites globally in the last 5 years.",
        "es": "HTTPS sigue siendo usado en menos del 20% de sitios web, con lentos avances en adopción.",
        "topic": "Web Security",
    },
    {
        "title": "OAuth 2.0 Security",
        "en": "OAuth 2.0 is vulnerable to authorization code interception attacks without PKCE.",
        "es": "OAuth 2.0 proporciona protección completa contra ataques de intercepción sin necesidad de PKCE.",
        "topic": "Web Security",
    },
    {
        "title": "Certificate Pinning Benefits",
        "en": "Certificate pinning prevents MITM attacks but requires careful key rotation planning.",
        "es": "El pinning de certificados es innecesario porque HTTPS ya previene todos los ataques MITM.",
        "topic": "Web Security",
    },
    {
        "title": "CORS Implementation",
        "en": "CORS headers are checked by browsers but can be bypassed by attackers making direct requests.",
        "es": "CORS proporciona protección del lado del servidor que no puede ser bypassed por solicitudes directas.",
        "topic": "Web Security",
    },
    {
        "title": "JWT Token Expiration",
        "en": "JWT tokens without expiration present infinite attack windows; short TTLs reduce exposure.",
        "es": "La expiración de JWT no importa porque el token se valida criptográficamente en cada solicitud.",
        "topic": "Web Security",
    },
    {
        "title": "Rate Limiting Strategy",
        "en": "IP-based rate limiting is ineffective against distributed DDoS attacks across many IPs.",
        "es": "El rate limiting basado en IP previene completamente los ataques DDoS distribuidos.",
        "topic": "Web Security",
    },
    {
        "title": "Content Security Policy",
        "en": "CSP headers prevent XSS attacks by restricting script execution to whitelisted sources.",
        "es": "Las CSP no previenen ataques XSS; solo proporcionan información sobre violaciones de seguridad.",
        "topic": "Web Security",
    },
    {
        "title": "HTTP Security Headers",
        "en": "Missing HTTP security headers like HSTS and X-Frame-Options leave applications vulnerable.",
        "es": "Los headers de seguridad HTTP son opcionales y no afectan la seguridad de la aplicación.",
        "topic": "Web Security",
    },
    {
        "title": "Password Hashing Algorithms",
        "en": "bcrypt and scrypt are intentionally slow to resist brute-force attacks on password hashes.",
        "es": "Los algoritmos de hashing rápido como MD5 son preferibles para almacenar contraseñas.",
        "topic": "Web Security",
    },
]

# Topic 4: Mobile Development
MOBILE_DEVELOPMENT_CONTRADICTIONS = [
    {
        "title": "Cross-Platform Framework Performance",
        "en": "Cross-platform frameworks like React Native have 10-30% performance overhead vs native code.",
        "es": "React Native ejecuta con el mismo rendimiento que el código nativo sin sobrecarga.",
        "topic": "Mobile Development",
    },
    {
        "title": "Native vs Hybrid Access",
        "en": "Native iOS and Android apps have unrestricted access to device APIs and sensors.",
        "es": "Las aplicaciones híbridas tienen acceso más amplio a los APIs del dispositivo que las aplicaciones nativas.",
        "topic": "Mobile Development",
    },
    {
        "title": "App Store Review Process",
        "en": "App Store review times average 24 hours; Google Play typically reviews within 2 hours.",
        "es": "Google Play reviews toman más tiempo que App Store, frecuentemente semanas.",
        "topic": "Mobile Development",
    },
    {
        "title": "Mobile Device Fragmentation",
        "en": "Android fragmentation across OS versions and device manufacturers complicates development significantly.",
        "es": "La fragmentación de Android es mínima debido a actualizaciones automáticas y estandarización de hardware.",
        "topic": "Mobile Development",
    },
    {
        "title": "Push Notification Delivery",
        "en": "FCM and APNs guarantee push notification delivery to the device within seconds.",
        "es": "Las notificaciones push no se garantizan; pueden perderse o entregarse con horas de retraso.",
        "topic": "Mobile Development",
    },
    {
        "title": "Battery Consumption Optimization",
        "en": "Location services in background mode consume 5-10x more battery than foreground services.",
        "es": "Los servicios de ubicación consume la misma batería independientemente de si están en primer o segundo plano.",
        "topic": "Mobile Development",
    },
    {
        "title": "App Size Constraints",
        "en": "App stores impose limits on initial download size, requiring on-demand feature delivery.",
        "es": "No hay límites de tamaño para descargas iniciales; todas las características se incluyen en el APK.",
        "topic": "Mobile Development",
    },
    {
        "title": "Offline-First Architecture",
        "en": "Offline-first apps require conflict resolution strategies when syncing changes from multiple devices.",
        "es": "Las arquitecturas offline-first se sincronizan automáticamente sin necesidad de manejo de conflictos.",
        "topic": "Mobile Development",
    },
    {
        "title": "Mobile Payment Integration",
        "en": "Apple Pay and Google Pay provide tokenization to protect card data during transmission.",
        "es": "Apple Pay y Google Pay transmiten números de tarjeta en texto plano, sin tokenización.",
        "topic": "Mobile Development",
    },
    {
        "title": "Progressive Web Apps",
        "en": "PWAs can replicate 80-90% of native app functionality using web technologies.",
        "es": "Las PWAs solo pueden implementar funcionalidad muy básica comparado con aplicaciones nativas.",
        "topic": "Mobile Development",
    },
]

# Topic 5: DevOps & Deployment
DEVOPS_CONTRADICTIONS = [
    {
        "title": "CI/CD Pipeline Automation",
        "en": "Automated CI/CD pipelines reduce deployment errors by 70-90% compared to manual processes.",
        "es": "La automatización de CI/CD aumenta los errores de implementación debido a falta de revisión humana.",
        "topic": "DevOps & Deployment",
    },
    {
        "title": "Container Image Scanning",
        "en": "Scanning container images for vulnerabilities at build time prevents exploitable code from reaching production.",
        "es": "El escaneo de contenedores en build time no es útil porque los CVE aparecen después del despliegue.",
        "topic": "DevOps & Deployment",
    },
    {
        "title": "Infrastructure as Code Benefits",
        "en": "IaC enables reproducible infrastructure deployments and simplifies disaster recovery procedures.",
        "es": "La infraestructura como código añade complejidad y no mejora la reproducibilidad.",
        "topic": "DevOps & Deployment",
    },
    {
        "title": "Blue-Green Deployment",
        "en": "Blue-green deployments enable zero-downtime updates by switching traffic between two environments.",
        "es": "Blue-green requiere downtime de sincronización entre los dos ambientes durante el switchover.",
        "topic": "DevOps & Deployment",
    },
    {
        "title": "Log Aggregation Importance",
        "en": "Centralized log aggregation is critical for debugging distributed systems and tracking security events.",
        "es": "La agregación de logs es una práctica opcional que no mejora significativamente el debugging.",
        "topic": "DevOps & Deployment",
    },
    {
        "title": "Canary Deployment Strategy",
        "en": "Canary deployments route a small percentage of traffic to new versions to detect issues early.",
        "es": "Las implementaciones canary requieren igual tiempo que despliegues abruptos, sin ventajas prácticas.",
        "topic": "DevOps & Deployment",
    },
    {
        "title": "Configuration Management Drift",
        "en": "Configuration drift occurs when servers diverge from desired state, causing inconsistency and bugs.",
        "es": "El drift de configuración es inevitable y no afecta negativamente la estabilidad del sistema.",
        "topic": "DevOps & Deployment",
    },
    {
        "title": "Rollback Procedure Speed",
        "en": "Automated rollback procedures can restore the previous version within minutes, minimizing impact.",
        "es": "Los rollbacks automatizados normalmente toman horas debido a validación y sincronización de datos.",
        "topic": "DevOps & Deployment",
    },
    {
        "title": "Monitoring & Alerting",
        "en": "Proactive monitoring with configurable alerts detects issues before they impact users.",
        "es": "El monitoreo generalmente se realiza manualmente después de que los usuarios reportan problemas.",
        "topic": "DevOps & Deployment",
    },
    {
        "title": "Load Balancer Persistence",
        "en": "Session persistence (sticky sessions) can cause uneven load distribution and should be avoided.",
        "es": "Las sesiones pegajosas son necesarias para mantener consistencia y mejorar la distribución de carga.",
        "topic": "DevOps & Deployment",
    },
]

# Non-contradictory filler topics (aligned translations)
NON_CONTRADICTORY_TOPICS = [
    {
        "title": "REST API Design Principles",
        "en": "REST APIs use HTTP methods (GET, POST, PUT, DELETE) to represent standard CRUD operations.",
        "es": "Las APIs REST utilizan métodos HTTP (GET, POST, PUT, DELETE) para representar operaciones CRUD estándar.",
    },
    {
        "title": "GraphQL vs REST",
        "en": "GraphQL allows clients to request exactly the data they need, reducing over-fetching.",
        "es": "GraphQL permite a los clientes solicitar exactamente los datos que necesitan, reduciendo la sobre-obtención.",
    },
    {
        "title": "Microservices Communication",
        "en": "Microservices communicate through APIs, message queues, or event streams.",
        "es": "Los microservicios se comunican a través de APIs, colas de mensajes o flujos de eventos.",
    },
    {
        "title": "API Rate Limiting",
        "en": "Rate limiting protects APIs from abuse by restricting requests per time window.",
        "es": "La limitación de velocidad protege las APIs del abuso restringiendo solicitudes por ventana de tiempo.",
    },
    {
        "title": "Caching Strategies",
        "en": "Caching at multiple layers (CDN, application, database) improves performance.",
        "es": "El almacenamiento en caché en múltiples capas (CDN, aplicación, base de datos) mejora el rendimiento.",
    },
    {
        "title": "Error Handling Standards",
        "en": "Standardized error codes and messages help clients handle failures gracefully.",
        "es": "Los códigos de error estandarizados y los mensajes ayudan a los clientes a manejar fallos correctamente.",
    },
    {
        "title": "API Documentation Tools",
        "en": "OpenAPI and Swagger enable automated API documentation and code generation.",
        "es": "OpenAPI y Swagger permiten documentación automatizada de API y generación de código.",
    },
    {
        "title": "Authentication Mechanisms",
        "en": "APIs use API keys, OAuth tokens, or mTLS for client authentication.",
        "es": "Las APIs utilizan claves API, tokens OAuth o mTLS para autenticación de clientes.",
    },
    {
        "title": "Request Validation",
        "en": "Input validation prevents injection attacks and ensures data integrity.",
        "es": "La validación de entrada previene ataques de inyección y asegura la integridad de datos.",
    },
    {
        "title": "Versioning Strategies",
        "en": "API versioning allows backward compatibility when introducing breaking changes.",
        "es": "El versionado de API permite compatibilidad hacia atrás al introducir cambios disruptivos.",
    },
    {
        "title": "Response Compression",
        "en": "Gzip compression reduces response payload sizes, improving bandwidth utilization.",
        "es": "La compresión gzip reduce el tamaño de las cargas útiles de respuesta, mejorando la utilización de ancho de banda.",
    },
    {
        "title": "Idempotent Operations",
        "en": "Idempotent operations produce the same result regardless of how many times they are executed.",
        "es": "Las operaciones idempotentes producen el mismo resultado sin importar cuántas veces se ejecuten.",
    },
    {
        "title": "Async Operations",
        "en": "Asynchronous API patterns allow long-running operations without blocking clients.",
        "es": "Los patrones asincrónosr de API permiten operaciones de larga duración sin bloquear clientes.",
    },
    {
        "title": "Health Check Endpoints",
        "en": "Health check endpoints enable monitoring systems to detect service failures.",
        "es": "Los puntos finales de verificación de salud permiten que los sistemas de monitoreo detecten fallos de servicio.",
    },
    {
        "title": "CORS Headers Configuration",
        "en": "CORS headers control which origins can access your API from browsers.",
        "es": "Los headers CORS controlan qué orígenes pueden acceder a tu API desde navegadores.",
    },
]


def generate_fresh_dataset(
    n_total_passages: int = 150,
    output_path: Path = Path("data/expanded/documents_fresh_150.parquet"),
    contradiction_ratio: float = 0.67,
) -> None:
    """Generate fresh dataset with new contradictions focused on 5 distinct topics.

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

    # Combine all contradiction sources
    all_contradictions = (
        CLOUD_CONTRADICTIONS
        + DATA_ANALYTICS_CONTRADICTIONS
        + WEB_SECURITY_CONTRADICTIONS
        + MOBILE_DEVELOPMENT_CONTRADICTIONS
        + DEVOPS_CONTRADICTIONS
    )

    rows = []
    row_id = 0

    print(f"Generating {n_total_passages} passages ({n_total_rows} pairs):")
    print(f"  - {n_contradictory_pairs} contradictory pairs ({n_contradictory_pairs * 2} passages)")
    print(f"  - {n_non_contradictory_pairs} non-contradictory pairs ({n_non_contradictory_pairs * 2} passages)")
    print(f"\nTopics covered:")
    print(f"  1. Cloud Infrastructure (10 contradictions)")
    print(f"  2. Data Analytics (10 contradictions)")
    print(f"  3. Web Security (10 contradictions)")
    print(f"  4. Mobile Development (10 contradictions)")
    print(f"  5. DevOps & Deployment (10 contradictions)")

    # 1. Contradictory pairs: cycle through all 50 unique contradictions
    for i in range(n_contradictory_pairs):
        base = all_contradictions[i % len(all_contradictions)]
        title = base["title"]
        topic = base["topic"]

        # EN row
        rows.append({
            "id_preproc": f"Tech_EN_{row_id}",
            "text": base["en"],
            "lang": "EN",
            "title": title,
            "topic": topic,
            "is_contradictory": True,
        })
        row_id += 1

        # ES row (contradictory counterpart)
        rows.append({
            "id_preproc": f"Tech_ES_{row_id}",
            "text": base["es"],
            "lang": "ES",
            "title": title,
            "topic": topic,
            "is_contradictory": True,
        })
        row_id += 1

    # 2. Non-contradictory pairs: use aligned translation topics
    for i in range(n_non_contradictory_pairs):
        topic = NON_CONTRADICTORY_TOPICS[i % len(NON_CONTRADICTORY_TOPICS)]
        title = topic["title"]

        # EN row
        rows.append({
            "id_preproc": f"Tech_EN_{row_id}",
            "text": topic["en"],
            "lang": "EN",
            "title": title,
            "topic": "General",
            "is_contradictory": False,
        })
        row_id += 1

        # ES row
        rows.append({
            "id_preproc": f"Tech_ES_{row_id}",
            "text": topic["es"],
            "lang": "ES",
            "title": title,
            "topic": "General",
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

    print(f"\nContradiction Distribution by Topic:")
    for topic in sorted(df[df['is_contradictory']]['topic'].unique()):
        count = (df[df['topic'] == topic]['is_contradictory']).sum() // 2
        print(f"  - {topic:25} {count:2} contradictory pairs")

    # Print sample rows
    print(f"\nSample rows:")
    for idx in [0, 1, len(df) // 2, len(df) - 2]:
        row = df.iloc[idx]
        print(f"\n  [{idx:3d}] {row['id_preproc']:10} | {row['lang']} | {row['topic']}")
        print(f"        Title: {row['title']}")
        print(f"        Contradictory: {row['is_contradictory']}")
        print(f"        Text: {row['text'][:75]}...")


if __name__ == "__main__":
    import sys

    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/expanded/documents_fresh_150.parquet")
    generate_fresh_dataset(output_path=output_path)
