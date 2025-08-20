# Real-Time Streaming Data Solution

**Kafka · Spark Structured Streaming · MinIO (S3-compatible)**

This project is my next step after the batch pipeline. I built an end-to-end **real-time streaming pipeline**: ingest JSON events into **Kafka**, process them with **Spark Structured Streaming** (event-time windows + watermarks), store **Parquet** in **MinIO (S3A)**, and publish **anomaly alerts** back to Kafka.

---

## 🔍 Problem Statement

Modern factories and services need **low-latency insights** from continuous event streams (devices, apps, services). That raises four challenges:

* **Reliable Ingestion:** Accept high-throughput events without loss.
* **Real-time Processing:** Do windowed aggregations and anomaly detection on **event time** (not arrival time).
* **Durable Storage:** Persist curated outputs in cost-effective **object storage** for downstream analytics.
* **Reproducibility:** Provide a one-command local stack for quick iteration.

---

## 🚀 My Learning Journey & Implementation

### 🧱 Step 1: Orchestrating the Environment with Docker Compose

I extended my Compose stack to include **Zookeeper, Kafka, MinIO, and Spark** (alongside my existing services). This created a local, production-like streaming environment.

* **Highlights:**

  * Added Kafka broker + Zookeeper; exposed internal bootstrap `kafka:9092`.
  * Added MinIO with `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` for S3A.
  * Ensured the Spark image includes Kafka & S3A connectors at submit time.
* **Verified UI access:**

  * **MinIO Console:** `http://localhost:9001`
  * **(Optional) Kafka UI:** `http://localhost:8080`

---

### 📡 Step 2: Ingesting Events into Kafka

I validated Kafka end-to-end, then built a Python producer to simulate device telemetry.

#### **Phase A — Quick Smoke Test (Console Tools)**

Create topics and confirm the broker works:

```bash
docker compose exec kafka \
  kafka-topics.sh --create --if-not-exists --bootstrap-server kafka:9092 \
  --replication-factor 1 --partitions 3 --topic sensor_events

docker compose exec kafka \
  kafka-topics.sh --create --if-not-exists --bootstrap-server kafka:9092 \
  --replication-factor 1 --partitions 3 --topic sensor_alerts
```

#### **Phase B — Realistic Stream (Python Producer)**

A lightweight generator publishes JSON like:

```json
{
  "device_id": "MTR-00123",
  "ts": "2025-08-17T12:34:56.789Z",
  "temperature_c": 78.6,
  "vibration_g": 0.12,
  "status": "OK",
  "site": "fab1",
  "line": "L01"
}
```

Run:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r producers/requirements.txt
python producers/generate_sensor_events.py \
  --brokers kafka:9092 --topic sensor_events --rate 50
```

---

### ⚙️ Step 3: Stream Processing with Spark Structured Streaming

I implemented a PySpark job that consumes `sensor_events` and applies **schema parsing, filters, event-time watermarks**, and **1-minute tumbling windows** per `device_id`.

* **Aggregations:** `count(*)`, `avg(temperature_c)`, `max(vibration_g)`
* **Anomaly routing:** if `temperature_c > 85` or `vibration_g > 0.5` → emit JSON to Kafka topic `sensor_alerts`
* **Why Structured Streaming:** higher-level DataFrame API, event-time semantics, and a unified batch/stream model (cleaner than legacy DStreams).

Run:

```bash
docker compose exec spark \
  spark-submit \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
  --conf spark.sql.shuffle.partitions=6 \
  --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 \
  --conf spark.hadoop.fs.s3a.access.key=$MINIO_ROOT_USER \
  --conf spark.hadoop.fs.s3a.secret.key=$MINIO_ROOT_PASSWORD \
  --conf spark.hadoop.fs.s3a.path.style.access=true \
  --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
  /app/streaming/job.py
```

> If your Spark image is 3.3/3.4, adjust the `spark-sql-kafka-0-10_2.12:<version>` coordinate.

---

### 🗄️ Step 4: Storing in MinIO (Object Storage) & Emitting Alerts to Kafka

* **Curated Parquet:** written to `s3a://rt-stream/curated/date=YYYY-MM-DD/hour=HH/…`
* **Checkpointing:** `s3a://rt-stream/_chk/` ensures exactly-once per micro-batch
* **Alerts:** real-time JSON events to `sensor_alerts` for downstream consumers

**Validation:**

* MinIO Console → bucket `rt-stream` → confirm `curated/` partitions and `_chk/`
* Kafka UI / console → confirm `sensor_alerts` messages

---

## 🛠️ Skills Gained

* **Kafka:** Topic design, console diagnostics, Python producer patterns.
* **Spark Structured Streaming:** Event-time windows, watermarks, Kafka source/sink, backpressure & checkpointing.
* **Object Storage (MinIO/S3A):** Partitioned Parquet, S3A configs, path-style access.
* **Containerization:** Multi-service orchestration with Docker Compose.
* **Operational Know-How:** Debugging connectivity, versioned connectors, and end-to-end validation.

---

## 📁 Repository Structure

```graphql
.
├── README.md
├── docker-compose.yml
├── .env.example
├── .env                # (untracked; keep it local)
├── .gitignore
│
├── data/
│   └── minio/          # persists MinIO objects
│
├── hadoop-conf/
│   ├── core-site.xml           # (if you have it)
│   ├── hdfs-site.xml           # (if you have it)
│   ├── hive-site.xml
│   ├── hadoop.env
│   ├── hive-start.sh
│   └── lib/
│       └── mysql-connector-j-8.x.jar
│
├── notebooks/
│   └── stream_checks.ipynb
│
├── producers/
│   ├── requirements.txt
│   └── generate_sensor_events.py
│
├── streaming/
│   └── job.py
│
└── configs/
    └── spark-defaults.conf
```

---

### 📈 Resume-Ready Summary

**Project:** Real-Time Streaming Data Solution
**Tech Stack:** Kafka, Spark Structured Streaming (PySpark), MinIO (S3A), Docker Compose, Python

* Built a real-time pipeline **Kafka → Spark Structured Streaming → MinIO**, using **event-time windows** and **watermarks**.
* Persisted **partitioned Parquet** with **S3A checkpointing**; routed **anomaly alerts** back to Kafka.
* Delivered a reproducible local environment via **Docker Compose** and validated through UIs/console tools.

---

### 📬 Next Steps

* [ ] Add Schema Registry (Avro/JSON Schema) and versioned producers
* [ ] Add Delta Lake / Apache Hudi sink for upserts on object storage
* [ ] Add Prometheus + Grafana (lag, throughput, latency)
* [ ] Add CI smoke test: produce → stream → assert Parquet partitions & alert rate

---
