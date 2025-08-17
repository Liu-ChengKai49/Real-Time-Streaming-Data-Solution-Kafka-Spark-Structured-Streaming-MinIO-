# Real-Time Streaming Data Solution (Kafka · Spark Structured Streaming · MinIO)

An end-to-end **streaming data pipeline** that ingests JSON events into **Kafka**, processes them with **Spark Structured Streaming (event-time windows, watermarks)**, and writes **Parquet** to **MinIO** (S3-compatible). The job also emits **anomaly alerts** back to Kafka. Built to practice real-time data engineering with reproducible, containerized tooling.

---

## 🔍 Problem Statement

Operational systems often require **low-latency insights** on continuous event streams:

* **Ingestion:** Reliable, scalable intake of device/app events.
* **Real-time processing:** Windowed aggregations and anomaly detection with event-time correctness.
* **Durable storage:** Cost-efficient object storage for curated parquet outputs.
* **Reproducibility:** One-command local stack to iterate quickly.

---

## 🚀 Implementation Overview

### 1) Orchestrate the environment (Docker Compose)

Containerized **Kafka (broker, UI)**, **MinIO (S3)**, and **Spark** into a local dev cluster for repeatable setup.
**UIs:** Kafka UI `:8080`, MinIO Console `:9001`.

---

### 2) Produce events to Kafka

A lightweight Python producer publishes JSON sensor events (device telemetry) to `sensor_events`.
Events include `device_id`, `ts` (UTC), `temperature_c`, `vibration_g`, `status`, `site`, `line`.

---

### 3) Stream processing with Spark

Spark Structured Streaming consumes `sensor_events`, applies **schema parsing**, **data cleaning**, **event-time watermarks**, and **1-minute tumbling windows** per `device_id`:

* **Aggregations:** count, average temperature, max vibration.
* **Anomaly detection:** if temperature > 85°C or vibration > 0.5g → emit JSON to `sensor_alerts`.
* **Sinks:**

  * Aggregations → **MinIO** (Parquet) under `s3a://rt-stream/curated/` (partitioned by date/hour).
  * Alerts → **Kafka** topic `sensor_alerts`.
* **Checkpointing:** `s3a://rt-stream/_chk/` for exactly-once per micro-batch.

---

## 🛠️ Skills Gained

* **Kafka:** Topic design, producers/consumers, operational checks with Kafka UI.
* **Spark Structured Streaming:** Event-time windows, watermarks, Kafka source/sink, Parquet sink.
* **Object storage (MinIO/S3A):** Writing partitioned Parquet, checkpointing.
* **Containerization:** Multi-service orchestration with Docker Compose.
* **Streaming reliability:** Idempotent writes, backpressure control, schema evolution basics.

---

## 🏁 Quickstart (local)

1. Start services:

   ```bash
   docker compose up -d
   ```

2. Create S3 bucket in MinIO Console at `http://localhost:9001` (e.g., `rt-stream`).

3. Create Kafka topics:

   ```bash
   docker compose exec kafka \
     kafka-topics.sh --create --if-not-exists --bootstrap-server kafka:9092 \
     --replication-factor 1 --partitions 3 --topic sensor_events

   docker compose exec kafka \
     kafka-topics.sh --create --if-not-exists --bootstrap-server kafka:9092 \
     --replication-factor 1 --partitions 3 --topic sensor_alerts
   ```

4. Start the Python event producer:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r producers/requirements.txt
   python producers/generate_sensor_events.py --rate 50 --topic sensor_events
   ```

5. Run the Spark streaming job:

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

6. Validate outputs:

   * **MinIO Console** → bucket `rt-stream` → `curated/` for Parquet partitions.
   * **Kafka UI** → topic `sensor_alerts` for anomaly messages.

> Exact producer/job code and configs live in this repo under `producers/`, `streaming/`, and `configs/`.

---

## 📁 Repository Structure

```txt
├── README.md                      # project overview & runbook
├── docker-compose.yml             # service orchestration (Kafka, UI, MinIO, Spark)
├── .env.example                   # env vars (Kafka, MinIO, Spark s3a)
│
├── configs/
│   └── spark-defaults.conf        # Spark defaults (Kafka, s3a options)
│
├── producers/
│   ├── requirements.txt           # kafka-python or confluent-kafka
│   └── generate_sensor_events.py  # JSON event generator (Kafka producer)
│
├── streaming/
│   └── job.py                     # Spark Structured Streaming (Kafka → MinIO + alerts)
│
├── schemas/
│   ├── sensor_event.json          # optional: JSON schema/Avro
│   └── alert_schema.json
│
└── notebooks/                     # optional: exploration/validation
    └── stream_checks.ipynb
```

---

## 📈 Resume-Ready Summary

**Project:** Real-Time Streaming Data Solution
**Stack:** Kafka, Spark Structured Streaming (PySpark), MinIO (S3A), Docker Compose, Python

* Built a real-time pipeline from **Kafka → Spark** with **event-time windows** and **watermarks**.
* Wrote curated **Parquet** to **MinIO (S3A)** with partitioning and checkpointing.
* Emitted **anomaly alerts** back to Kafka for downstream consumers.
* Reproducible local environment via Docker Compose (broker, UI, object store, Spark).

---

## 🗺️ Next Steps

* [ ] Add Schema Registry (Confluent or Redpanda) and evolve event schemas
* [ ] Stateful anomaly scoring (device baselines)
* [ ] Delta Lake / Apache Hudi sink (upserts on object storage)
* [ ] Prometheus + Grafana dashboards (lag, throughput, latency)
* [ ] CI smoke test: produce → stream → assert Parquet counts & alert rate
