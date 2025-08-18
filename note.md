docker compose down
docker compose up -d




4) Health checks

# Kafka list (inside broker)
docker compose exec kafka kafka-topics.sh --bootstrap-server kafka:9092 --list

# MinIO console -> open in browser
# http://localhost:9001  (login with MINIO_ROOT_USER / MINIO_ROOT_PASSWORD)

# Kafka UI -> open in browser
# http://localhost:8080 (cluster "local" should show topics list)