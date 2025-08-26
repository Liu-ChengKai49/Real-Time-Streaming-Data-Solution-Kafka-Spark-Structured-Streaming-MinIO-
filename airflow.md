Perfect—since your **streaming** project doesn’t run Airflow, we’ll wire lineage **directly from Spark** to **Marquez**. Here’s the full A→G guide, tailored to your `docker-compose.yml` (no Airflow needed).

---

# A) Scope & naming (5 min)

* **Namespace:** use `dev` (or `dev-stream` if you want to separate later).
* **Job names:** Spark → `spark.app.name` is used (OL appends action names).
* **Datasets:**

  * **Kafka topics (inputs):** OpenLineage will name them by **cluster + topic**. Expect a dataset with namespace like `kafka://kafka:9092` and name like `sensor_events`. ([OpenLineage][1])
  * **MinIO/S3 paths (outputs):** Use the full URI you write to, e.g. `s3a://rt-stream/curated/sensor_kpi_5min/`. Spark integration captures filesystem URIs automatically. ([OpenLineage][2])
* **Tier/tag:** in your repo metadata (e.g., `docs/metadata/metadata.yml`), mark curated tables/paths with `tier: curated` so they stand out.

---

# B) Stand up Marquez (10 min)

Add these **three services** to the **same compose file** (your streaming stack) and the same network (`big-data-net`), then bring them up:

```yaml
# --- add under services: ---
  marquez-db:
    image: postgres:14
    environment:
      - POSTGRES_PASSWORD=marquez
      - POSTGRES_DB=marquez
    ports: ["5433:5432"]                # avoid clash with local Postgres
    networks: [big-data-net]

  marquez:
    image: marquezproject/marquez:latest
    environment:
      - MARQUEZ_DB_HOST=marquez-db
      - MARQUEZ_DB_PORT=5432
      - MARQUEZ_PORT=5000
    depends_on: [marquez-db]
    ports: ["5000:5000"]
    networks: [big-data-net]

  marquez-web:
    image: marquezproject/marquez-web:latest
    environment:
      - MARQUEZ_HOST=marquez
      - MARQUEZ_PORT=5000
    depends_on: [marquez]
    ports: ["3000:3000"]
    networks: [big-data-net]
```

Bring them up:

```bash
docker compose up -d marquez-db marquez marquez-web
```

Open the UI at **[http://localhost:3000](http://localhost:3000)** to confirm it’s running. ([GitHub][3], [peppy-sprite-186812.netlify.app][4], [OpenLineage][5])

---

# C) Enable OpenLineage in **Spark** (10 min)

You’ll add the OpenLineage **Spark listener** at submit time:

```bash
docker compose exec -it spark bash

# example spark-submit for your streaming job:
spark-submit \
  --packages io.openlineage:openlineage-spark:1.37.0 \
  --conf spark.extraListeners=io.openlineage.spark.agent.OpenLineageSparkListener \
  --conf spark.openlineage.transport.type=http \
  --conf spark.openlineage.transport.url=http://marquez:5000 \
  --conf spark.openlineage.namespace=dev \
  --conf spark.app.name=stream_sensor_kpi \
  /app/streaming/stream_to_minio.py \
    --brokers kafka:9092 \
    --topic sensor_events \
    --s3 s3a://rt-stream/curated/sensor_kpi_5min/
```

* `--packages …openlineage-spark:1.37.0` adds the listener jar.
* `spark.extraListeners=…OpenLineageSparkListener` turns it on.
* `spark.openlineage.transport.url` points at the **Marquez API** (`marquez:5000` inside the network) and `transport.type=http` uses HTTP transport.
* `spark.openlineage.namespace=dev` sets your job namespace.
  These flags come directly from the official Spark integration guide and config reference. ([OpenLineage][2])

> Tip: You already persist Ivy/Maven caches (`spark_ivy`, `spark_m2`), so the first `--packages` resolve will be cached for future runs.

---

# D) Emit lineage from your tasks (20 min)

No Airflow needed—your **Spark Structured Streaming** job will auto-emit lineage:

* **Kafka source** → dataset `(namespace=kafka://kafka:9092, name=sensor_events)`. ([OpenLineage][1])
* **MinIO sink** → dataset `s3a://rt-stream/curated/sensor_kpi_5min/`. ([OpenLineage][2])
* OpenLineage for Spark supports filesystem, JDBC, Kafka, and more out of the box via the listener; you don’t have to instrument your code for basic lineage. ([OpenLineage][2])

**Keep sink paths stable** (no random suffixes in output dirs) so the dataset name remains constant across runs.

---

# E) Smoke test (5 min)

1. Start Marquez (Step B) and your stack (Kafka, MinIO, Spark).
2. Produce a few messages to the topic (your `python-producer` or any simple script).
3. Run the `spark-submit` above and let it write to `s3a://rt-stream/curated/sensor_kpi_5min/`.
4. Open **Marquez Web** at **[http://localhost:3000](http://localhost:3000)** and select namespace **`dev`**. You should see:

   * **Job(s):** names derived from `spark.app.name` + Spark action, e.g., `stream_sensor_kpi.execute_insert_into_hadoop_fs_relation_command`. ([OpenLineage][2])
   * **Datasets:** `kafka://kafka:9092` / `sensor_events` → `s3a://rt-stream/curated/sensor_kpi_5min/`.
   * **Run state:** `COMPLETE` (or `FAIL`—still useful for debugging).

---

# F) Tiny health check (3 min)

If you want a quick check in CI/local scripts that Marquez API is reachable:

```bash
# Just verify the API responds (don’t assume the 'dev' namespace exists yet)
curl -sf http://localhost:5000/api/v1/namespaces >/dev/null
```

(That endpoint is served by the Marquez API on port **5000**.) ([OpenLineage][5])

---

# G) Make it useful for incidents (10 min)

Add a short **runbook** to your repo, e.g. `docs/lineage.md`:

```md
# Streaming Lineage Runbook

- **Namespace:** dev
- **Jobs:** Spark app `stream_sensor_kpi` (OpenLineage appends action names)
- **Input dataset:** Kafka topic `sensor_events` on `kafka://kafka:9092`
- **Output dataset:** `s3a://rt-stream/curated/sensor_kpi_5min/`
- **UI:** Marquez → http://localhost:3000 (Jobs tab → search `stream_sensor_kpi`)

## When output looks wrong
1) In Marquez, open the latest job run and inspect **Upstream** to see which dataset / topic delivered records.
2) Click the input dataset to see **recent producing jobs**.
3) Cross-check the **logical plan facet** for major query changes. 
```

(Those job/dataset views and facets are exactly what Marquez exposes in the UI.) ([OpenLineage][2])

---

## Why this works

* **Spark integration path**: OpenLineage uses a **SparkListener** to auto-collect inputs/outputs and job metadata; you just load the jar and provide `spark.openlineage.*` configs. ([OpenLineage][2])
* **Marquez UI**: centralized, web-based lineage graph on **:3000**; API on **:5000**. ([GitHub][3], [OpenLineage][5])

---

If you want, I can also give you a **ready-to-paste `spark-submit` wrapper** (bash) and a minimal **streaming PySpark script** that reads `sensor_events` and writes 5-minute KPIs to `s3a://rt-stream/curated/sensor_kpi_5min/`, already tuned for lineage-friendly naming.

[1]: https://openlineage.io/apidocs/javadoc/io/openlineage/client/dataset/Naming.Kafka.html?utm_source=chatgpt.com "Naming.Kafka (openlineage-java 1.35.0-SNAPSHOT API)"
[2]: https://openlineage.io/docs/guides/spark "Using OpenLineage with Spark | OpenLineage"
[3]: https://github.com/MarquezProject/marquez/blob/main/README.md?utm_source=chatgpt.com "README.md - MarquezProject/marquez"
[4]: https://peppy-sprite-186812.netlify.app/docs/quickstart?utm_source=chatgpt.com "Quickstart"
[5]: https://openlineage.io/docs/1.22.0/guides/airflow-backfill-dags/?utm_source=chatgpt.com "Backfilling Airflow DAGs Using Marquez"
