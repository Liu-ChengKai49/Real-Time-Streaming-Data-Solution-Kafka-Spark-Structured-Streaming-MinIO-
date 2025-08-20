#!/usr/bin/env python3
from pyspark.sql import SparkSession, functions as F, types as T
import os

# ── Config (env vars with safe defaults) ────────────────────────────────────────
BROKERS        = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
SRC_TOPIC      = os.getenv("SOURCE_TOPIC", "sensor_events")
ALERT_TOPIC    = os.getenv("ALERT_TOPIC", "sensor_alerts")
BUCKET_ROOT    = os.getenv("S3_BUCKET_ROOT", "s3a://rt-stream")
CURATED_PATH   = os.getenv("CURATED_PATH",  f"{BUCKET_ROOT}/curated")
CHK_ROOT       = os.getenv("CHECKPOINT_ROOT", f"{BUCKET_ROOT}/_chk")
OFFSETS_PER_T  = os.getenv("MAX_OFFSETS_PER_TRIGGER")     # e.g. "1000" to throttle
START_OFFSETS  = os.getenv("STARTING_OFFSETS", "latest")  # "latest" or "earliest"

# Dev-friendly defaults (override via env for prod)
WINDOW         = os.getenv("WINDOW", "30 seconds")        # e.g. "1 minute"
WATERMARK      = os.getenv("WATERMARK", "30 seconds")     # e.g. "2 minutes"
TRIGGER        = os.getenv("TRIGGER", "10 seconds")       # e.g. "30 seconds"
DEBUG_SINKS    = os.getenv("DEBUG_SINKS", "1")            # "1" to print to console

# ── Spark session ───────────────────────────────────────────────────────────────
spark = (
    SparkSession.builder
    .appName("rt-stream:events->parquet+alerts")
    # tip: move connector & S3A configs to spark-submit flags
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")

# ── Source: Kafka ───────────────────────────────────────────────────────────────
src = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", BROKERS)
    .option("subscribe", SRC_TOPIC)
    .option("startingOffsets", START_OFFSETS)
    .option("failOnDataLoss", "false")
)
if OFFSETS_PER_T:
    src = src.option("maxOffsetsPerTrigger", OFFSETS_PER_T)

raw = src.load().select(
    F.col("key").cast("string").alias("k"),
    F.col("value").cast("string").alias("v")
)

# ── Parse JSON payload ──────────────────────────────────────────────────────────
# Include optional event_ts in schema to avoid FIELD_NOT_FOUND when referenced.
schema = T.StructType([
    T.StructField("device_id",      T.StringType(),  True),
    T.StructField("ts",             T.StringType(),  True),  # ISO8601 '...Z' or with offset
    T.StructField("event_ts",       T.StringType(),  True),  # optional alternate timestamp
    T.StructField("temperature_c",  T.DoubleType(),  True),
    T.StructField("vibration_g",    T.DoubleType(),  True),
    T.StructField("status",         T.StringType(),  True),
    T.StructField("site",           T.StringType(),  True),
    T.StructField("line",           T.StringType(),  True),
])

json = F.from_json(F.col("v"), schema).alias("j")

# Robust ISO-8601 parse: accept ts with/without millis, or event_ts if present
event_ts_expr = F.coalesce(
    F.to_timestamp(F.col("j.ts"),       "yyyy-MM-dd'T'HH:mm:ss.SSSX"),   # with ms
    F.to_timestamp(F.col("j.ts"),       "yyyy-MM-dd'T'HH:mm:ssX"),       # no ms
    F.to_timestamp(F.col("j.event_ts"), "yyyy-MM-dd'T'HH:mm:ss[.SSS]X")  # alternate field
).alias("event_ts")

events = (
    raw.select(json)
       .select(
           F.col("j.device_id").alias("device_id"),
           event_ts_expr,
           F.col("j.temperature_c").alias("temperature_c"),
           F.col("j.vibration_g").alias("vibration_g"),
           F.col("j.status").alias("status"),
           F.col("j.site").alias("site"),
           F.col("j.line").alias("line"),
       )
       # Basic sanity filters
       .where("event_ts IS NOT NULL")
       .where("temperature_c IS NULL OR (temperature_c > -50 AND temperature_c < 150)")
       .where("vibration_g IS NULL OR vibration_g >= 0")
)

# ── (Optional) Debug sinks so you SEE rows during development ───────────────────
if DEBUG_SINKS == "1":
    events.writeStream.format("console").outputMode("append").option("truncate", False).start()

# ── Alerts: HOT or VIB ─────────────────────────────────────────────────────────
alerts_df = (
    events
    .filter( (F.col("temperature_c") > 85) | (F.col("vibration_g") > 0.5) )
    .select(
        F.col("device_id").alias("key"),
        F.to_json(F.struct(
            "device_id","event_ts","temperature_c","vibration_g","status","site","line"
        )).alias("value")
    )
    .select(F.col("key").cast("string"), F.col("value").cast("string"))
)

alerts_q = (
    alerts_df.writeStream.format("kafka")
    .option("kafka.bootstrap.servers", BROKERS)
    .option("topic", ALERT_TOPIC)
    .option("checkpointLocation", f"{CHK_ROOT}/alerts")
    .outputMode("append")
    .start()
)

# ── Aggregations: tumbling window per device_id ─────────────────────────────────
agg = (
    events
    .withWatermark("event_ts", WATERMARK)                  # tolerate late data
    .groupBy(
        F.window("event_ts", WINDOW).alias("w"),           # e.g. "30 seconds" or "1 minute"
        F.col("device_id")
    )
    .agg(
        F.count("*").alias("n_events"),
        F.avg("temperature_c").alias("avg_temperature_c"),
        F.max("vibration_g").alias("max_vibration_g"),
    )
    .select(
        F.col("device_id"),
        F.col("n_events"),
        F.col("avg_temperature_c"),
        F.col("max_vibration_g"),
        F.col("w.start").alias("window_start"),
        F.col("w.end").alias("window_end"),
    )
    .withColumn("date", F.date_format("window_start", "yyyy-MM-dd"))
    .withColumn("hour", F.date_format("window_start", "HH"))
)

if DEBUG_SINKS == "1":
    # 'complete' gives you a full table snapshot per trigger (great for dev)
    agg.writeStream.format("console").outputMode("complete").option("truncate", False).start()

# ── Curated Parquet sink to MinIO (S3A) ─────────────────────────────────────────
curated_q = (
    agg.writeStream
    .format("parquet")
    .option("path", CURATED_PATH)                          # e.g. s3a://rt-stream/curated
    .option("checkpointLocation", f"{CHK_ROOT}/curated")   # e.g. s3a://rt-stream/_chk/curated
    .partitionBy("date","hour")
    .outputMode("append")                                  # required with watermark'd windows
    .trigger(processingTime=TRIGGER)                       # frequent batches in dev
    .start()
)

spark.streams.awaitAnyTermination()
