from pyspark.sql import SparkSession
from pyspark.sql.functions import col
spark = (SparkSession.builder.appName("kafka->console").getOrCreate())
spark.sparkContext.setLogLevel("INFO")
df = (spark.readStream.format("kafka")
      .option("kafka.bootstrap.servers","kafka:9092")
      .option("subscribe","sensor_events")
      .option("startingOffsets","latest")
      .load()
      .selectExpr("CAST(key AS STRING) AS key", "CAST(value AS STRING) AS value"))
q = (df.writeStream.format("console")
      .option("truncate","false").option("numRows","5")
      .outputMode("append").start())
q.awaitTermination()
