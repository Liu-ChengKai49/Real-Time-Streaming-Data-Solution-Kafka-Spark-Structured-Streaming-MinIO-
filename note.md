docker compose down
docker compose build spark
docker compose up -d



<!-- 2) Start the Spark streaming job (keep this terminal open) -->

docker compose exec spark bash -lc '
  export HOME=/tmp/spark-home
  /opt/bitnami/spark/bin/spark-submit \
    --master local[*] \
    --conf spark.jars.ivy=$HOME/.ivy2 \
    --conf spark.pyspark.python=/usr/bin/python3 \
    --conf spark.pyspark.driver.python=/usr/bin/python3 \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 \
    --conf spark.hadoop.fs.s3a.path.style.access=true \
    --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
    --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false \
    --conf spark.hadoop.fs.s3a.access.key=$MINIO_ROOT_USER \
    --conf spark.hadoop.fs.s3a.secret.key=$MINIO_ROOT_PASSWORD \
    /app/streaming/job.py
'



<!-- 3) Produce fresh events while Spark is running -->
docker compose run --rm python-producer bash -lc \
  "pip install -r producers/requirements.txt && \
   python producers/generate_sensor_events.py \
     --brokers kafka:9092 --topic sensor_events --rate 50 --duration 60"


<!-- 4) Read the alerts -->
docker compose exec -T kafka \
  kafka-console-consumer.sh --bootstrap-server kafka:9092 \
  --topic sensor_alerts --from-beginning --timeout-ms 8000 \
  --property print.key=true --property key.separator=' | '

